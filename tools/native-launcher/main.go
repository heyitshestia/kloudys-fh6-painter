package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const appFolderName = "KloudysFH6Painter"

type pythonCandidate struct {
	exe  string
	args []string
}

func main() {
	appDir, err := findAppDir()
	if err != nil {
		showError(err.Error())
		os.Exit(1)
	}

	launcherScript := filepath.Join(appDir, "launcher_qt.py")
	if !fileExists(launcherScript) {
		showError("KFPS could not find launcher_qt.py.\n\nExpected location:\n" + launcherScript)
		os.Exit(1)
	}

	python, err := findPython(appDir)
	if err != nil {
		showError(err.Error())
		os.Exit(1)
	}

	logFile := openLog(appDir)
	if logFile != nil {
		defer logFile.Close()
		logLine(logFile, "appDir=%s", appDir)
		logLine(logFile, "python=%s", python.exe)
		logLine(logFile, "script=%s", launcherScript)
	}

	args := append([]string{}, python.args...)
	args = append(args, launcherScript)
	cmd := exec.Command(python.exe, args...)
	cmd.Dir = appDir
	if logFile != nil {
		cmd.Stdout = logFile
		cmd.Stderr = logFile
	}
	if err := cmd.Start(); err != nil {
		logLine(logFile, "start failed: %v", err)
		showError("KFPS could not start the launcher.\n\n" + err.Error())
		os.Exit(1)
	}

	done := make(chan error, 1)
	go func() {
		done <- cmd.Wait()
	}()

	select {
	case err := <-done:
		exitText := "unknown exit"
		if cmd.ProcessState != nil {
			exitText = fmt.Sprintf("exit code %d", cmd.ProcessState.ExitCode())
		}
		if err != nil {
			logLine(logFile, "launcher_qt.py exited immediately: %s, %v", exitText, err)
		} else {
			logLine(logFile, "launcher_qt.py exited immediately: %s", exitText)
		}
		message := "KFPS Launcher started Python, but the app closed immediately.\n\n"
		if logFile != nil {
			message += "Check this log:\n" + logFile.Name()
		} else {
			message += exitText
		}
		showError(message)
		os.Exit(1)
	case <-time.After(1500 * time.Millisecond):
		logLine(logFile, "launcher_qt.py is still running after startup check")
		focusChildWindow(uint32(cmd.Process.Pid), logFile)
	}
}

func findAppDir() (string, error) {
	exePath, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("KFPS could not resolve its launcher path.\n\n%w", err)
	}
	baseDir := filepath.Dir(exePath)
	nested := filepath.Join(baseDir, appFolderName)
	if fileExists(filepath.Join(nested, "launcher_qt.py")) {
		return nested, nil
	}
	if fileExists(filepath.Join(baseDir, "launcher_qt.py")) {
		return baseDir, nil
	}
	return "", errors.New("KFPS could not find the app folder.\n\nPut this launcher next to the KloudysFH6Painter folder, then try again.")
}

func findPython(appDir string) (pythonCandidate, error) {
	candidates := []pythonCandidate{
		{exe: filepath.Join(appDir, "python", "pythonw.exe")},
		{exe: filepath.Join(appDir, "python", "python.exe")},
	}
	if localAppData := os.Getenv("LOCALAPPDATA"); localAppData != "" {
		candidates = append(candidates,
			pythonCandidate{exe: filepath.Join(localAppData, "Programs", "Python", "Python312", "pythonw.exe")},
			pythonCandidate{exe: filepath.Join(localAppData, "Programs", "Python", "Python312", "python.exe")},
		)
	}
	candidates = append(candidates,
		pythonCandidate{exe: "py.exe", args: []string{"-3.12"}},
		pythonCandidate{exe: "py", args: []string{"-3.12"}},
		pythonCandidate{exe: "pythonw.exe"},
		pythonCandidate{exe: "python.exe"},
		pythonCandidate{exe: "python"},
	)

	for _, candidate := range candidates {
		if !isOnPathOrFile(candidate.exe) {
			continue
		}
		if pythonOK(candidate) {
			return candidate, nil
		}
	}

	return pythonCandidate{}, errors.New("KFPS could not find usable Python 3.12.\n\nRun KloudysFH6Painter\\01_add_python312_to_path.bat, then open this launcher again.")
}

func pythonOK(candidate pythonCandidate) bool {
	args := append([]string{}, candidate.args...)
	args = append(args, "-c", "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)")
	cmd := exec.Command(candidate.exe, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	return cmd.Run() == nil
}

func isOnPathOrFile(path string) bool {
	if strings.ContainsAny(path, `\/`) {
		return fileExists(path)
	}
	_, err := exec.LookPath(path)
	return err == nil
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

func openLog(appDir string) *os.File {
	runtimeDir := filepath.Join(appDir, "runtime")
	if err := os.MkdirAll(runtimeDir, 0755); err != nil {
		return nil
	}
	path := filepath.Join(runtimeDir, "launcher-native.log")
	file, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return nil
	}
	logLine(file, "--- KFPS native launcher %s ---", time.Now().Format(time.RFC3339))
	return file
}

func logLine(file *os.File, format string, args ...interface{}) {
	if file == nil {
		return
	}
	_, _ = fmt.Fprintf(file, format+"\n", args...)
	_ = file.Sync()
}

func focusChildWindow(pid uint32, logFile *os.File) {
	if runtime.GOOS != "windows" {
		return
	}
	user32 := syscall.NewLazyDLL("user32.dll")
	enumWindows := user32.NewProc("EnumWindows")
	getWindowThreadProcessID := user32.NewProc("GetWindowThreadProcessId")
	isWindowVisible := user32.NewProc("IsWindowVisible")
	showWindow := user32.NewProc("ShowWindow")
	setForegroundWindow := user32.NewProc("SetForegroundWindow")
	allowSetForegroundWindow := user32.NewProc("AllowSetForegroundWindow")

	const (
		swRestore = 9
		asfwAny   = 0xFFFFFFFF
	)

	allowSetForegroundWindow.Call(asfwAny)

	deadline := time.Now().Add(4 * time.Second)
	for time.Now().Before(deadline) {
		var found uintptr
		cb := syscall.NewCallback(func(hwnd uintptr, lparam uintptr) uintptr {
			var windowPID uint32
			getWindowThreadProcessID.Call(hwnd, uintptr(unsafe.Pointer(&windowPID)))
			if windowPID != pid {
				return 1
			}
			visible, _, _ := isWindowVisible.Call(hwnd)
			if visible == 0 {
				return 1
			}
			found = hwnd
			return 0
		})
		enumWindows.Call(cb, 0)
		if found != 0 {
			showWindow.Call(found, swRestore)
			setForegroundWindow.Call(found)
			logLine(logFile, "focused launcher window hwnd=0x%x", found)
			return
		}
		time.Sleep(150 * time.Millisecond)
	}
	logLine(logFile, "no visible launcher window found for pid=%d during focus handoff", pid)
}

func showError(message string) {
	user32 := syscall.NewLazyDLL("user32.dll")
	messageBox := user32.NewProc("MessageBoxW")
	title, _ := syscall.UTF16PtrFromString("KFPS Launcher")
	text, _ := syscall.UTF16PtrFromString(message)
	messageBox.Call(0, uintptr(unsafe.Pointer(text)), uintptr(unsafe.Pointer(title)), 0x10)
}
