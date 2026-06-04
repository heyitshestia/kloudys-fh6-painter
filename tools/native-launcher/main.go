package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
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

	args := append([]string{}, python.args...)
	args = append(args, launcherScript)
	cmd := exec.Command(python.exe, args...)
	cmd.Dir = appDir
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	if err := cmd.Start(); err != nil {
		showError("KFPS could not start the launcher.\n\n" + err.Error())
		os.Exit(1)
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

func showError(message string) {
	user32 := syscall.NewLazyDLL("user32.dll")
	messageBox := user32.NewProc("MessageBoxW")
	title, _ := syscall.UTF16PtrFromString("KFPS Launcher")
	text, _ := syscall.UTF16PtrFromString(message)
	messageBox.Call(0, uintptr(unsafe.Pointer(text)), uintptr(unsafe.Pointer(title)), 0x10)
}
