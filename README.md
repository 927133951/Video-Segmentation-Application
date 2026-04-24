# 视频分割软件 / Video Segmentation Software

## 项目介绍 / Project Introduction

视频分割软件是一款功能强大的视频分割工具，支持按时间长度和基于语音内容的智能分割，帮助用户快速将长视频切割成多个短视频片段。

Video Segmentation Software is a powerful video splitting tool that supports both time-based and speech-based intelligent segmentation, helping users quickly cut long videos into multiple short video clips.

## 功能特性 / Features

- **按时间长度分割**：用户可以设置每段视频的时长，软件会自动按设定时长分割视频
- **基于语音内容的智能分割**：根据语音停顿、对话间隙和语义完整性自动调整分割点，确保语音段落不被截断
- **图形化界面**：直观易用的界面，支持拖拽操作和实时进度显示
- **多种视频格式支持**：支持MP4、AVI、MOV、MKV、WMV、FLV等多种视频格式
- **智能进度显示**：实时显示分割进度和剩余时间
- **详细的日志记录**：记录分割过程中的每一步操作和可能的错误

- **Time-based segmentation**: Users can set the duration of each video segment, and the software will automatically split the video according to the set duration
- **Speech-based intelligent segmentation**: Automatically adjust segmentation points based on speech pauses, dialogue gaps, and semantic integrity to ensure speech segments are not truncated
- **Graphical interface**: Intuitive and easy-to-use interface with drag-and-drop operations and real-time progress display
- **Multiple video format support**: Supports MP4, AVI, MOV, MKV, WMV, FLV and other video formats
- **Intelligent progress display**: Real-time display of segmentation progress and remaining time
- **Detailed log recording**: Records every step of the segmentation process and possible errors

## 系统要求 / System Requirements

- **操作系统**：Windows 7/8/10/11
- **CPU**：Intel Core i3或同等性能处理器
- **内存**：至少4GB RAM
- **存储空间**：至少100MB可用空间
- **GPU**：支持CUDA的GPU（推荐，可加速处理）
- **依赖**：FFmpeg（软件已内置）

- **Operating System**: Windows 7/8/10/11
- **CPU**: Intel Core i3 or equivalent processor
- **Memory**: At least 4GB RAM
- **Storage**: At least 100MB free space
- **GPU**: CUDA-supported GPU (recommended for accelerated processing)
- **Dependencies**: FFmpeg (built-in)

## 安装说明 / Installation Instructions

### 方法1：直接使用可执行文件（推荐） / Method 1: Use Executable File (Recommended)

1. 从[发布页面](https://github.com/yourusername/video-segmentation-software/releases)下载最新版本的`视频分割软件.exe`
2. 双击运行`视频分割软件.exe`文件
3. 软件会自动解压并启动，无需安装

1. Download the latest version of `视频分割软件.exe` from the [releases page](https://github.com/yourusername/video-segmentation-software/releases)
2. Double-click to run `视频分割软件.exe`
3. The software will automatically extract and start, no installation required

### 方法2：从源码运行 / Method 2: Run from Source Code

1. 克隆仓库：`git clone https://github.com/yourusername/video-segmentation-software.git`
2. 安装依赖：`pip install -r requirements.txt`
3. 运行：`python main.py`

1. Clone the repository: `git clone https://github.com/yourusername/video-segmentation-software.git`
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python main.py`

## 使用方法 / Usage

### 基本操作 / Basic Operations

1. **选择视频文件**：点击"选择视频文件"按钮，浏览并选择要分割的视频文件
2. **设置分割参数**：
   - 在"单段时长(分钟)"输入框中输入每段视频的时长
   - 勾选"基于语音内容分割（智能分割）"选项以启用智能分割
3. **选择保存路径**：点击"选择保存路径"按钮，选择分割后视频的保存位置
4. **开始分割**：点击"开始分割"按钮，软件开始分割视频
5. **查看结果**：分割完成后，软件会显示完成提示，分割后的视频会保存在指定的保存路径中

1. **Select video file**: Click the "选择视频文件" button, browse and select the video file to be segmented
2. **Set segmentation parameters**:
   - Enter the duration of each video segment in the "单段时长(分钟)" input box
   - Check the "基于语音内容分割（智能分割）" option to enable intelligent segmentation
3. **Select save path**: Click the "选择保存路径" button, select the save location for the segmented videos
4. **Start segmentation**: Click the "开始分割" button, the software starts to segment the video
5. **View results**: After segmentation is completed, the software will display a completion prompt, and the segmented videos will be saved in the specified save path

### 智能分割说明 / Intelligent Segmentation Instructions

智能分割功能使用FFmpeg提取音频并分析语音停顿，自动在合适的位置分割视频，确保：
- 对话不被截断
- 语义内容完整
- 分割点自然流畅

The intelligent segmentation feature uses FFmpeg to extract audio and analyze speech pauses, automatically segmenting videos at appropriate positions to ensure:
- Dialogue is not truncated
- Semantic content is complete
- Segmentation points are natural and smooth

## 工作原理 / Working Principle

### 按时间分割 / Time-based Segmentation

1. 使用FFmpeg命令按指定时长分割视频
2. 保持视频和音频的原始质量
3. 自动生成带序号的输出文件名

1. Uses FFmpeg commands to segment video by specified duration
2. Maintains original quality of video and audio
3. Automatically generates output filenames with sequence numbers

### 基于语音内容分割 / Speech-based Segmentation

1. 提取视频中的音频
2. 分析音频的能量和静音点
3. 识别对话间隙和语义边界
4. 在合适的位置分割视频
5. 确保分割点不破坏语音内容的完整性

1. Extracts audio from video
2. Analyzes audio energy and silence points
3. Identifies dialogue gaps and semantic boundaries
4. Segments video at appropriate positions
5. Ensures segmentation points do not break the integrity of speech content

## 技术栈 / Technology Stack

- **开发语言**：Python 3.12
- **GUI框架**：PyQt5
- **视频处理**：FFmpeg
- **打包工具**：PyInstaller
- **图标设计**：自定义ICO图标

- **Development Language**: Python 3.12
- **GUI Framework**: PyQt5
- **Video Processing**: FFmpeg
- **Packaging Tool**: PyInstaller
- **Icon Design**: Custom ICO icon

## 常见问题 / FAQ

### 1. 软件运行时提示缺少FFmpeg？

软件已内置FFmpeg，无需单独安装。如果仍然出现此提示，请确保：
- 软件文件完整，没有被杀毒软件隔离
- 以管理员身份运行软件

### 1. Software prompts missing FFmpeg when running?

FFmpeg is built into the software and does not need to be installed separately. If you still see this prompt, please ensure:
- The software files are complete and not quarantined by antivirus software
- Run the software as an administrator

### 2. 分割后的视频没有声音？

这可能是因为FFmpeg处理时出现问题。请尝试：
- 检查原始视频是否有音频
- 尝试使用不同的视频格式
- 确保软件有足够的权限写入文件

### 2. Segmented videos have no sound?

This may be due to issues with FFmpeg processing. Please try:
- Check if the original video has audio
- Try using a different video format
- Ensure the software has sufficient permissions to write files

### 3. 智能分割效果不理想？

智能分割的效果取决于视频的音频质量。对于以下情况，建议使用按时间分割：
- 视频中有大量背景噪音
- 多人同时说话
- 音频质量较差

### 3. Intelligent segmentation效果 is not ideal?

The effectiveness of intelligent segmentation depends on the audio quality of the video. For the following cases, it is recommended to use time-based segmentation:
- Video has a lot of background noise
- Multiple people speaking at the same time
- Poor audio quality

## 贡献指南 / Contribution Guidelines

欢迎提交Issue和Pull Request来改进这个项目。

1. Fork 仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 打开一个Pull Request

Contributions are welcome! Please feel free to submit Issues and Pull Requests to improve this project.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 许可证 / License

本项目采用MIT许可证。详见[LICENSE](LICENSE)文件。

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## 联系方式 / Contact

- 项目地址：[https://github.com/927133951/Video-Segmentation-Application.git](https://github.com/927133951/Video-Segmentation-Application.git)
- 问题反馈：[Issues页面](https://github.com/927133951/Video-Segmentation-Application/issues)

- Project URL: [https://github.com/927133951/Video-Segmentation-Application.git](https://github.com/927133951/Video-Segmentation-Application.git)
- Issue Tracker: [Issues page](https://github.com/927133951/Video-Segmentation-Application/issues)

---

**感谢使用视频分割软件！**

**Thank you for using Video Segmentation Software!**