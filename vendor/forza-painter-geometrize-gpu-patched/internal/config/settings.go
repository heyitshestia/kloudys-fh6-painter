package config

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"forza-painter-geometrize-go/internal/model"
)

func DefaultSettings() model.Settings {
	return model.Settings{
		Description:       "Default profile",
		DetailMode:        "normal",
		MaxPreviewSize:    500,
		MaxResolution:     2000,
		MaxThreads:        0,
		MutatedSamples:    1000,
		ForceOpaqueShapes: true,
		PosterizeLevels:   20,
		PreviewEvery:      10,
		RandomSamples:     3000,
		SaveAt:            map[int]struct{}{500: {}, 1000: {}, 1500: {}, 2000: {}, 2500: {}, 3000: {}},
		SaveEvery:         10,
		ShapeMode:         "mixed_ellipses",
		StopAt:            3000,
		UseWorkGroupEval:  true,
	}
}

func ResolveSettingsPath(rootDir, explicitPath, profile string) (string, error) {
	if explicitPath != "" {
		return explicitPath, nil
	}

	settingsDir := filepath.Join(rootDir, "settings")
	if profile != "" {
		matches, err := os.ReadDir(settingsDir)
		if err != nil {
			return "", err
		}
		needle := strings.ToLower(profile)
		for _, entry := range matches {
			if entry.IsDir() {
				continue
			}
			name := strings.ToLower(entry.Name())
			if strings.Contains(name, needle) && strings.HasSuffix(name, ".ini") {
				return filepath.Join(settingsDir, entry.Name()), nil
			}
		}
		return "", fmt.Errorf("profile %q not found in %s", profile, settingsDir)
	}

	return filepath.Join(settingsDir, "_default.ini"), nil
}

func ParseSettings(path string) (model.Settings, error) {
	cfg := DefaultSettings()
	file, err := os.Open(path)
	if err != nil {
		return cfg, err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") || strings.HasPrefix(line, ";") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		value := strings.TrimSpace(parts[1])

		switch key {
		case "description":
			cfg.Description = value
		case "detailMode":
			cfg.DetailMode = strings.TrimSpace(value)
		case "maxPreviewSize":
			cfg.MaxPreviewSize = parseInt(value, cfg.MaxPreviewSize)
		case "maxResolution":
			cfg.MaxResolution = parseInt(value, cfg.MaxResolution)
		case "maxThreads":
			cfg.MaxThreads = parseInt(value, cfg.MaxThreads)
		case "mutatedSamples":
			cfg.MutatedSamples = parseInt(value, cfg.MutatedSamples)
		case "forceOpaqueShapes":
			cfg.ForceOpaqueShapes = parseBool(value, cfg.ForceOpaqueShapes)
		case "posterizeLevels":
			cfg.PosterizeLevels = parseInt(value, cfg.PosterizeLevels)
		case "previewEvery":
			cfg.PreviewEvery = parseInt(value, cfg.PreviewEvery)
		case "randomSamples":
			cfg.RandomSamples = parseInt(value, cfg.RandomSamples)
		case "saveAt":
			cfg.SaveAt = parseSaveAt(value)
		case "saveEvery":
			cfg.SaveEvery = parseInt(value, cfg.SaveEvery)
		case "shapeMode":
			cfg.ShapeMode = strings.TrimSpace(value)
		case "stopAt":
			cfg.StopAt = parseInt(value, cfg.StopAt)
		case "useWorkGroupEval":
			cfg.UseWorkGroupEval = parseBool(value, cfg.UseWorkGroupEval)
		}
	}
	if err := scanner.Err(); err != nil {
		return cfg, err
	}

	if cfg.RandomSamples < 1 {
		cfg.RandomSamples = 1
	}
	if cfg.MutatedSamples < 0 {
		cfg.MutatedSamples = 0
	}
	if cfg.StopAt < 1 {
		cfg.StopAt = 1
	}
	if cfg.SaveEvery < 1 {
		cfg.SaveEvery = 1
	}
	if strings.TrimSpace(cfg.ShapeMode) == "" {
		cfg.ShapeMode = "mixed_ellipses"
	}
	if strings.TrimSpace(cfg.DetailMode) == "" {
		cfg.DetailMode = "normal"
	}

	return cfg, nil
}
func parseInt(value string, fallback int) int {
	n, err := strconv.Atoi(strings.TrimSpace(value))
	if err != nil {
		return fallback
	}
	return n
}

func parseBool(value string, fallback bool) bool {
	v := strings.TrimSpace(strings.ToLower(value))
	switch v {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return fallback
	}
}

func parseSaveAt(value string) map[int]struct{} {
	out := make(map[int]struct{})
	for _, part := range strings.Split(value, ",") {
		n, err := strconv.Atoi(strings.TrimSpace(part))
		if err != nil || n < 1 {
			continue
		}
		out[n] = struct{}{}
	}
	if len(out) == 0 {
		out[3000] = struct{}{}
	}
	return out
}
