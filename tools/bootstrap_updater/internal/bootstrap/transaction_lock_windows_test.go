//go:build windows

package bootstrap

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"syscall"
	"testing"
	"time"
)

func holdDestinationReadOnly(t *testing.T, path string) func() {
	t.Helper()
	pointer, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		t.Fatal(err)
	}
	handle, err := syscall.CreateFile(pointer, syscall.GENERIC_READ, syscall.FILE_SHARE_READ, nil, syscall.OPEN_EXISTING, syscall.FILE_ATTRIBUTE_NORMAL, 0)
	if err != nil {
		t.Fatal(err)
	}
	var once sync.Once
	release := func() {
		once.Do(func() { syscall.CloseHandle(handle) })
	}
	t.Cleanup(release)
	return release
}

func lockedTransactionFixture(t *testing.T) (*Transaction, Layout, string, string, string) {
	t.Helper()
	install, state, staging := t.TempDir(), t.TempDir(), t.TempDir()
	layout := Layout{InstallRoot: install, AppRoot: filepath.Join(install, "KloudysFH6Painter")}
	first, last := filepath.Join(layout.AppRoot, "program.txt"), filepath.Join(install, "KFPS-Updater.exe")
	writeTestFile(t, first, "old-program")
	writeTestFile(t, last, "old-updater")
	writeTestFile(t, filepath.Join(staging, "program"), "new-program")
	writeTestFile(t, filepath.Join(staging, "updater"), "new-updater")
	tx, err := NewTransaction(state, "locked-update", layout, []Change{
		{Kind: ReplaceFile, Destination: first, Staged: filepath.Join(staging, "program")},
		{Kind: ReplaceFile, Destination: last, Staged: filepath.Join(staging, "updater")},
	}, testLogger(t, state, "locked-update"))
	if err != nil {
		t.Fatal(err)
	}
	return tx, layout, state, first, last
}

func TestLockedDestinationStopsBeforeAnyInstallationWrite(t *testing.T) {
	tx, _, _, first, last := lockedTransactionFixture(t)
	holdDestinationReadOnly(t, last)
	if err := tx.Prepare(); err == nil {
		t.Fatal("locked destination passed preflight")
	}
	assertFileContent(t, first, "old-program")
	assertFileContent(t, last, "old-updater")
}

func TestRollbackSkipsLockedUnchangedDestination(t *testing.T) {
	tx, _, state, first, last := lockedTransactionFixture(t)
	if err := tx.Prepare(); err != nil {
		t.Fatal(err)
	}
	holdDestinationReadOnly(t, last)
	if err := tx.Apply(); err == nil {
		t.Fatal("late destination lock was ignored")
	}
	if err := tx.Rollback(); err != nil {
		t.Fatalf("unchanged locked file prevented rollback: %v", err)
	}
	assertFileContent(t, first, "old-program")
	assertFileContent(t, last, "old-updater")
	if fileExists(filepath.Join(state, "current-transaction.json")) {
		t.Fatal("completed rollback left journal")
	}
}

func TestFailedRollbackRetainsRecoveryUntilLockCloses(t *testing.T) {
	tx, layout, state, first, last := lockedTransactionFixture(t)
	if err := tx.Prepare(); err != nil {
		t.Fatal(err)
	}
	if err := tx.Apply(); err != nil {
		t.Fatal(err)
	}
	release := holdDestinationReadOnly(t, last)
	if err := tx.Rollback(); err == nil {
		t.Fatal("changed locked file unexpectedly rolled back")
	}
	payload, err := os.ReadFile(filepath.Join(state, "current-transaction.json"))
	if err != nil {
		t.Fatal(err)
	}
	var journal transactionJournal
	if err := json.Unmarshal(payload, &journal); err != nil {
		t.Fatal(err)
	}
	if journal.Status == "rolled-back" {
		t.Fatal("failed rollback was marked complete")
	}
	if !fileExists(tx.journal.Operations[1].Backup) {
		t.Fatal("failed rollback lost its backup")
	}
	release()
	if recovered, err := RecoverInterruptedTransaction(state, layout, tx.logger); err != nil || !recovered {
		t.Fatalf("retry failed: %v %v", recovered, err)
	}
	assertFileContent(t, first, "old-program")
	assertFileContent(t, last, "old-updater")
}

func TestLegacyRolledBackJournalWithBackupsIsReverified(t *testing.T) {
	tx, layout, state, first, last := lockedTransactionFixture(t)
	if err := tx.Prepare(); err != nil {
		t.Fatal(err)
	}
	if err := tx.Apply(); err != nil {
		t.Fatal(err)
	}
	tx.journal.Status = "rolled-back"
	if err := tx.writeJournal(); err != nil {
		t.Fatal(err)
	}
	if recovered, err := RecoverInterruptedTransaction(state, layout, tx.logger); err != nil || !recovered {
		t.Fatalf("legacy rollback recovery failed: %v %v", recovered, err)
	}
	assertFileContent(t, first, "old-program")
	assertFileContent(t, last, "old-updater")
}

func TestTransientDestinationLocksAreRetried(t *testing.T) {
	for _, phase := range []string{"prepare", "apply"} {
		t.Run(phase, func(t *testing.T) {
			tx, _, _, first, last := lockedTransactionFixture(t)
			if phase == "apply" {
				if err := tx.Prepare(); err != nil {
					t.Fatal(err)
				}
			}
			release := holdDestinationReadOnly(t, last)
			timer := time.AfterFunc(250*time.Millisecond, release)
			defer timer.Stop()
			if phase == "prepare" {
				if err := tx.Prepare(); err != nil {
					t.Fatal(err)
				}
			}
			if err := tx.Apply(); err != nil {
				t.Fatal(err)
			}
			if err := tx.Commit(); err != nil {
				t.Fatal(err)
			}
			assertFileContent(t, first, "new-program")
			assertFileContent(t, last, "new-updater")
		})
	}
}

func TestLegacyRollbackMissingBackupRetainsRemainingRecovery(t *testing.T) {
	tx, layout, state, _, _ := lockedTransactionFixture(t)
	if err := tx.Prepare(); err != nil {
		t.Fatal(err)
	}
	if err := tx.Apply(); err != nil {
		t.Fatal(err)
	}
	tx.journal.Status = "rolled-back"
	if err := tx.writeJournal(); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(tx.journal.Operations[0].Backup); err != nil {
		t.Fatal(err)
	}
	if _, err := RecoverInterruptedTransaction(state, layout, tx.logger); err == nil {
		t.Fatal("missing backup was silently accepted")
	}
	if !fileExists(tx.journalPath) || !fileExists(tx.journal.Operations[1].Backup) {
		t.Fatal("incomplete recovery discarded remaining evidence")
	}
}

func TestRollbackJournalWriteFailurePreservesBackup(t *testing.T) {
	tx, _, _, first, last := lockedTransactionFixture(t)
	if err := tx.Prepare(); err != nil {
		t.Fatal(err)
	}
	if err := tx.Apply(); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(tx.journalPath); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(tx.journalPath, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := tx.Rollback(); err == nil {
		t.Fatal("journal failure was ignored")
	}
	if !fileExists(tx.journal.Operations[1].Backup) {
		t.Fatal("journal failure lost backup")
	}
	assertFileContent(t, first, "new-program")
	assertFileContent(t, last, "new-updater")
}
