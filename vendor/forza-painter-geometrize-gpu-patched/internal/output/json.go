package output

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"forza-painter-geometrize-go/internal/model"
)

func SaveGeometry(path string, shapes []model.Shape) error {
	payload := model.Geometry{Shapes: shapes}
	data, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}

func BuildOutputPath(basePath string, shapeCount int) string {
	ext := filepath.Ext(basePath)
	name := basePath[:len(basePath)-len(ext)]
	return fmt.Sprintf("%s.%d.json", name, shapeCount)
}

func BuildFinalOutputPath(basePath string) string {
	ext := filepath.Ext(basePath)
	name := basePath[:len(basePath)-len(ext)]
	return name + ".json"
}
