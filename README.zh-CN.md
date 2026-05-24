# Kloudy's FH6 Painter

[English](README.md) | [中文](README.zh-CN.md)

把图片生成 Forza Horizon 6 可导入的 Vinyl JSON，并把 JSON 写入当前打开的 FH6 Vinyl Group Editor 模板。

完整英文说明见 [docs/USER_MANUAL.md](docs/USER_MANUAL.md)。下面是中文简版。

## 鸣谢 / Credits

本项目建立在多个上游项目和贡献者的工作之上。许可证和原始声明保留在 [LICENSE](LICENSE) 和 [LICENSE.geometrize-gpu](LICENSE.geometrize-gpu)。

| 人 / 项目 | 链接 | 贡献 |
| --- | --- | --- |
| AE / A-Dawg#0001 | https://github.com/forza-painter/forza-painter | 原始 Forza Painter、MIT 许可的 FH 导入流程、内存写入/导入基础、图像转 Vinyl 的核心思路。 |
| BVZRays / bvz rays | https://github.com/bvzrays/forza-painter-fh6 | 本项目主要上游 FH6 桌面版本，包括 FH6 UI 流程、导入/定位、发布打包、文档和应用行为。 |
| zjl88858 / forza-painter-geometrize-gpu | https://github.com/zjl88858/forza-painter-geometrize-gpu | GPU/OpenCL geometrize 生成器来源，当前打包的 `forza-painter-geometrize-go.exe` 基于这一类工作流。 |
| Sam Twidale | https://samcodes.co.uk/ | `geometrize-lib` 作者，项目许可证中保留原始署名。 |
| Michael Fogleman | https://github.com/fogleman/primitive | `primitive` 作者，项目许可证中保留原始署名。 |
| Sanguk Ko / ree9622 | https://github.com/ree9622 | BVZRays 上游历史中的韩语本地化贡献者。 |
| heyitshestia / Kloudy | https://github.com/heyitshestia/kloudys-fh6-painter | 当前 fork：Luma Bands、V2 checkpoint/finalize 调整、Targeted repair 默认开启、checkpoint 浏览器、更新脚本、预设/UI 调整、主题支持和 FH6 导入安全处理。 |

## 先安装

必须先装 **64 位 Python 3.12**：

https://www.python.org/downloads/release/python-31210/

然后按顺序双击：

```text
01_add_python312_to_path.bat
02_install_dependencies.bat
04_start_app.bat
```

不要先打开软件。不要先打开游戏。先把 Python 3.12 和依赖装好。

如果软件打不开，运行：

```text
05_check_environment.bat
```

## 更新

只用这个文件更新：

```text
03_update_from_github.bat
```

更新前先关闭软件。不要手动拖文件覆盖更新。更新脚本会从 GitHub 拉取最新文件，并保留生成结果和运行数据。

如果电脑没有 Git，更新脚本会自动为当前 Windows 用户安装 PortableGit。

## 基本流程

1. 打开 `04_start_app.bat`。
2. 在 `Generate JSON` 页面选择一张图片。
3. 选择品质预设，或者开启自定义设置。
4. 默认建议保持 `Luma Bands` 和 `Targeted repair` 开启。
5. 点击开始生成。
6. 在 FH6 里进入 `Create Vinyl Group` / `Vinyl Group Editor`。
7. 加载足够层数的简单模板，并且 `Ungroup`。
8. 回到软件 `Import` 页面。
9. 选择生成好的 JSON，填写游戏里显示的真实模板层数。
10. 点击导入。

## FH6 导入重点

FH6 需要额外 **4 个边界层**，所以可用图形层数是：

```text
模板总层数 - 4
```

例如：

| 模板层数 | 可用图形层数 |
| ---: | ---: |
| 500 | 496 |
| 1000 | 996 |
| 2000 | 1996 |
| 3000 | 2996 |

导入时模板必须已经 `Ungroup`，并且必须停留在 Vinyl Group Editor。

## 当前预设

| 预设 | 输出层数 | 随机样本 | 用途 |
| --- | ---: | ---: | --- |
| Extremely fast | 500 | 30000 | 快速看构图 |
| Fast | 1000 | 60000 | 快速草稿 |
| Balanced | 1800 | 120000 | 日常默认 |
| Slow | 2500 | 220000 | 成品质量 |
| Super slow | 3000 | 350000 | 最高内置质量 |

如果画面糊，优先增加 `Random samples`，然后再提高输出层数和分辨率。

## 功能解释

- `Luma Bands`：预处理输入图，按亮度分段，适合动漫、平涂、边界明显的图片。不适合非常柔和的渐变照片。
- `Targeted repair`：生成后修复边界、透明洞、手指缝、头发缝等容易出错的位置。默认开启。
- `vroom vroom scrrrrt zoooom!`：增加采样等努力参数，但不改变输出层数和分辨率。
- `Checkpoint browser`：按生成文件夹浏览旧 checkpoint，重启软件后也会扫描 `imgs` 文件夹。

## 常见问题

- 软件打不开：重新运行 `01_add_python312_to_path.bat` 和 `02_install_dependencies.bat`。
- 预览不可用：通常是预览依赖问题，不一定影响生成和导入。
- 找不到游戏：先启动 FH6，再刷新 Import 页面。
- 权限错误：用管理员身份运行 `04_start_app.bat`。
- 提示没 Ungroup：检查是否真的在 Vinyl Group Editor、层数是否完全正确、有没有切换菜单。
- 导入后被截断：模板层数不够。
- 导入后太糊：生成层数或采样太低，或者导入了低层数 checkpoint。

## 示例

示例图片在 [docs/examples/test-finest](docs/examples/test-finest)。

| 原图 | 生成结果 |
| --- | --- |
| <img src="docs/examples/test-finest/miku-original.png" width="360" alt="Miku 原图"> | <img src="docs/examples/test-finest/miku-vinyl.png" width="360" alt="Miku 生成结果"> |
| <img src="docs/examples/test-finest/pokemon-original.png" width="360" alt="Pokemon 原图"> | <img src="docs/examples/test-finest/pokemon-vinyl.png" width="360" alt="Pokemon 生成结果"> |
