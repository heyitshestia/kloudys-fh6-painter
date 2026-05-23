package model

type Settings struct {
	Description       string
	DetailMode        string
	MaxPreviewSize    int
	MaxResolution     int
	MaxThreads        int
	MutatedSamples    int
	ForceOpaqueShapes bool
	PosterizeLevels   int
	PreviewEvery      int
	RandomSamples     int
	SaveAt            map[int]struct{}
	SaveEvery         int
	ShapeMode         string
	StopAt            int
	UseWorkGroupEval  bool
}

type Shape struct {
	Type  int     `json:"type"`
	Data  []int   `json:"data"`
	Color []int   `json:"color"`
	Score float64 `json:"score"`
}

type Geometry struct {
	Shapes []Shape `json:"shapes"`
}

type Candidate struct {
	Type  int
	X     float32
	Y     float32
	RX    float32
	RY    float32
	Theta float32
	R     float32
	G     float32
	B     float32
	A     float32
}
