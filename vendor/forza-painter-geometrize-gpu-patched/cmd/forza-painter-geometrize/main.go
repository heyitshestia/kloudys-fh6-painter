package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"forza-painter-geometrize-go/internal/engine"
)

func main() {
	settingsPath := flag.String("settings", "", "Path to settings ini file")
	profile := flag.String("profile", "", "Profile name fragment under ./settings")
	outputPath := flag.String("output", "", "Output path prefix (default: input image path)")
	previewPath := flag.String("preview", "", "Optional preview PNG output path")
	seed := flag.Int64("seed", 0, "Optional RNG seed for reproducible output")
	flag.Parse()
	applyTrailingOptions(flag.Args()[1:], settingsPath, profile, outputPath, previewPath, seed)

	if flag.NArg() < 1 {
		fmt.Println("Usage: forza-painter-geometrize [--settings path.ini|--profile name] [--output path] [--preview path] [--seed n] <image-path>")
		os.Exit(1)
	}

	imagePath := flag.Arg(0)
	absRoot, _ := os.Getwd()

	opts := engine.Options{
		ImagePath:     imagePath,
		SettingsPath:  *settingsPath,
		Profile:       *profile,
		OutputPath:    normalizeOutput(*outputPath),
		PreviewPath:   normalizePreviewPath(*previewPath),
		WorkspaceRoot: absRoot,
		Seed:          *seed,
	}

	if err := engine.Run(opts); err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("FINISHED")
}

func normalizeOutput(path string) string {
	if path == "" {
		return ""
	}
	if filepath.IsAbs(path) {
		return path
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		return path
	}
	return abs
}

func normalizePreviewPath(path string) string {
	abs := normalizeOutput(path)
	if abs == "" {
		return ""
	}
	if strings.HasSuffix(abs, string(os.PathSeparator)) {
		return filepath.Join(abs, "preview.png")
	}
	if info, err := os.Stat(abs); err == nil && info.IsDir() {
		return filepath.Join(abs, "preview.png")
	}
	return abs
}

func applyTrailingOptions(extra []string, settingsPath, profile, outputPath, previewPath *string, seed *int64) {
	for i := 0; i < len(extra); i++ {
		arg := extra[i]
		next := func() (string, bool) {
			if i+1 >= len(extra) {
				return "", false
			}
			i++
			return extra[i], true
		}

		switch arg {
		case "--settings", "-settings":
			if v, ok := next(); ok {
				*settingsPath = v
			}
		case "--profile", "-profile":
			if v, ok := next(); ok {
				*profile = v
			}
		case "--output", "-output":
			if v, ok := next(); ok {
				*outputPath = v
			}
		case "--preview", "-preview":
			if v, ok := next(); ok {
				*previewPath = v
			}
		case "--seed", "-seed":
			if v, ok := next(); ok {
				var parsed int64
				if _, err := fmt.Sscanf(v, "%d", &parsed); err == nil {
					*seed = parsed
				}
			}
		}
	}
}
