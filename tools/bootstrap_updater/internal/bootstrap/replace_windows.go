//go:build windows

package bootstrap

import (
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const (
	moveFileReplaceExisting = 0x1
	moveFileWriteThrough    = 0x8
)

var moveFileEx = syscall.NewLazyDLL("kernel32.dll").NewProc("MoveFileExW")

func retryWindowsFileLock(action func() error) error {
	deadline := time.Now().Add(3 * time.Second)
	for {
		err := action()
		if err == nil || (!errors.Is(err, syscall.Errno(5)) && !errors.Is(err, syscall.Errno(32)) && !errors.Is(err, syscall.Errno(33))) || !time.Now().Before(deadline) {
			return err
		}
		time.Sleep(100 * time.Millisecond)
	}
}

func checkReplaceableFile(path string) error {
	path, err := extendedWindowsPath(path)
	if err != nil {
		return err
	}
	pointer, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return err
	}
	return retryWindowsFileLock(func() error {
		const deleteAccess = 0x00010000
		handle, err := syscall.CreateFile(pointer, deleteAccess, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE|syscall.FILE_SHARE_DELETE, nil, syscall.OPEN_EXISTING, syscall.FILE_FLAG_OPEN_REPARSE_POINT, 0)
		if err != nil {
			return err
		}
		return syscall.CloseHandle(handle)
	})
}

func replaceFile(source, destination string) error {
	var err error
	source, err = extendedWindowsPath(source)
	if err != nil {
		return err
	}
	destination, err = extendedWindowsPath(destination)
	if err != nil {
		return err
	}
	sourcePointer, err := syscall.UTF16PtrFromString(source)
	if err != nil {
		return err
	}
	destinationPointer, err := syscall.UTF16PtrFromString(destination)
	if err != nil {
		return err
	}
	return retryWindowsFileLock(func() error {
		result, _, callErr := moveFileEx.Call(
			uintptr(unsafe.Pointer(sourcePointer)),
			uintptr(unsafe.Pointer(destinationPointer)),
			uintptr(moveFileReplaceExisting|moveFileWriteThrough),
		)
		if result == 0 {
			return fmt.Errorf("MoveFileExW failed: %w", callErr)
		}
		return nil
	})
}

func extendedWindowsPath(value string) (string, error) {
	absolute, err := filepath.Abs(value)
	if err != nil {
		return "", err
	}
	absolute = filepath.Clean(absolute)
	if strings.HasPrefix(absolute, `\\?\`) || strings.HasPrefix(absolute, `\\.\`) {
		return absolute, nil
	}
	if strings.HasPrefix(absolute, `\\`) {
		return `\\?\UNC\` + strings.TrimPrefix(absolute, `\\`), nil
	}
	return `\\?\` + absolute, nil
}
