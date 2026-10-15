import sys
import os
import math
import shutil
import subprocess
import json
import tempfile
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QProgressBar,
    QTextEdit, QGroupBox, QFormLayout, QMessageBox, QCheckBox
)
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QIcon

class VideoSegmentationWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, video_path, output_dir, segment_duration, video_duration=0, use_speech_based_segmentation=False):
        super().__init__()
        self.video_path = video_path
        self.output_dir = output_dir
        self.segment_duration = segment_duration
        self.video_duration = video_duration
        self.use_speech_based_segmentation = use_speech_based_segmentation
        self._cancelled = False
        self._proc = None

    def cancel(self):
        self._cancelled = True
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except OSError:
                pass

    def run(self):
        try:
            if self.use_speech_based_segmentation:
                self._segment_based_on_speech()
            else:
                self._segment_based_on_time()
        except Exception as e:
            if not self._cancelled:
                self.error.emit(f"错误: {str(e)}")

    def _run_ffmpeg(self, cmd):
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding='utf-8',
            errors='ignore'
        )
        self._proc = process
        err_output = process.stderr.read()
        process.wait()
        self._proc = None
        return process.returncode, err_output

    def _segment_based_on_time(self):
        try:
            base_name, ext = os.path.splitext(os.path.basename(self.video_path))
            output_pattern = os.path.join(self.output_dir, f"{base_name}_part_%03d{ext}")
            cmd = [
                "ffmpeg",
                "-y",
                "-i", self.video_path,
                "-map", "0",
                "-c", "copy",
                "-segment_time", str(self.segment_duration),
                "-f", "segment",
                "-reset_timestamps", "1",
                output_pattern
            ]
            error_output = []
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                encoding='utf-8',
                errors='ignore'
            )
            self._proc = process
            while True:
                if self._cancelled:
                    process.terminate()
                    process.wait()
                    self._proc = None
                    self.finished.emit("分割已取消")
                    return
                output = process.stderr.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    error_output.append(output)
                    if "time=" in output and self.video_duration > 0:
                        try:
                            time_str = output.split("time=")[1].split(" ")[0]
                            h, m, s = map(float, time_str.split(":"))
                            current_time = h * 3600 + m * 60 + s
                            progress = min(int(current_time / self.video_duration * 100), 100)
                            self.progress.emit(progress)
                        except (ValueError, IndexError):
                            pass
            self._proc = None
            process.wait()
            if self._cancelled:
                self.finished.emit("分割已取消")
            elif process.returncode == 0:
                self.finished.emit("视频分割完成！")
            else:
                error_message = ''.join(error_output[-15:]).strip() or "未知错误"
                self.error.emit(f"分割失败: {error_message}")
        except Exception as e:
            if not self._cancelled:
                self.error.emit(f"错误: {str(e)}")

    def _segment_based_on_speech(self):
        temp_audio = None
        try:
            self.progress.emit(5)
            fd, temp_audio = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            extract_cmd = [
                "ffmpeg",
                "-y",
                "-i", self.video_path,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                temp_audio
            ]
            code, err = self._run_ffmpeg(extract_cmd)
            if self._cancelled:
                self.finished.emit("分割已取消")
                return
            if code != 0:
                raise Exception(f"音频提取失败: {(err or '').strip()[-500:]}")
            self.progress.emit(15)
            silence_points = self._detect_silence_improved(temp_audio)
            self.progress.emit(55)
            if self._cancelled:
                self.finished.emit("分割已取消")
                return
            cut_points = self._determine_smart_segment_points(silence_points)
            self.progress.emit(60)
            boundaries = [0.0]
            for point in cut_points:
                keyframe = self._snap_to_keyframe(point)
                if keyframe > boundaries[-1] + 1.0:
                    boundaries.append(keyframe)
            boundaries.append(self._resolve_duration())
            base_name, ext = os.path.splitext(os.path.basename(self.video_path))
            total = len(boundaries) - 1
            for i in range(total):
                if self._cancelled:
                    self.finished.emit("分割已取消")
                    return
                output_file = os.path.join(self.output_dir, f"{base_name}_part_{i:03d}{ext}")
                segment_cmd = self._build_segment_command(
                    self.video_path,
                    output_file,
                    boundaries[i],
                    boundaries[i + 1]
                )
                code, err = self._run_ffmpeg(segment_cmd)
                if self._cancelled:
                    self.finished.emit("分割已取消")
                    return
                if code != 0:
                    raise Exception(f"分割第 {i + 1} 段失败: {(err or '').strip()[-500:]}")
                self.progress.emit(min(60 + int((i + 1) / total * 38), 98))
            self.progress.emit(100)
            self.finished.emit("基于语音内容的智能视频分割完成！")
        except Exception as e:
            if self._cancelled:
                self.finished.emit("分割已取消")
            else:
                self.error.emit(f"基于语音内容分割失败: {str(e)}")
        finally:
            if temp_audio and os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                except OSError:
                    pass

    def _build_segment_command(self, input_file, output_file, start, end):
        return [
            "ffmpeg",
            "-y",
            "-ss", f"{start:.3f}",
            "-i", input_file,
            "-t", f"{max(end - start, 0.1):.3f}",
            "-map", "0",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            output_file
        ]

    def _snap_to_keyframe(self, t):
        if t <= 0:
            return 0.0
        try:
            window = max(0.0, t - 30)
            cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-skip_frame", "nokey",
                "-show_entries", "frame=pts_time",
                "-of", "csv=p=0",
                "-read_intervals", f"{window}%{t}",
                self.video_path
            ]
            result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='ignore')
            times = []
            for line in result.stdout.splitlines():
                try:
                    times.append(float(line.strip()))
                except ValueError:
                    pass
            if times:
                return times[-1]
        except OSError:
            pass
        return t

    def _detect_silence_improved(self, audio_file):
        silence_sets = []
        silence_set1 = self._detect_silence_with_params(audio_file, "-25dB", 0.5)
        silence_sets.append(silence_set1)
        silence_set2 = self._detect_silence_with_params(audio_file, "-35dB", 0.3)
        silence_sets.append(silence_set2)
        silence_set3 = self._detect_silence_with_params(audio_file, "-30dB", 1.0)
        silence_sets.append(silence_set3)
        all_silence = []
        for s_set in silence_sets:
            all_silence.extend(s_set)
        unique_silence = sorted(set(all_silence))
        filtered_silence = []
        for point in unique_silence:
            if not filtered_silence or point - filtered_silence[-1] >= 0.5:
                filtered_silence.append(point)
        return filtered_silence

    def _detect_silence_with_params(self, audio_file, threshold, min_duration):
        cmd = [
            "ffmpeg",
            "-i", audio_file,
            "-af", f"silencedetect=n={threshold}:d={min_duration}",
            "-f", "null",
            "-"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        silence_points = []
        for line in result.stderr.split('\n'):
            if "silence_end" in line:
                try:
                    end = float(line.split('silence_end: ')[1].split(' ')[0])
                    silence_points.append(end)
                except (ValueError, IndexError):
                    pass
        return silence_points

    def _determine_smart_segment_points(self, silence_points):
        cut_points = []
        current_start = 0.0
        video_duration = self._resolve_duration()
        dialogue_breaks = []
        for i, point in enumerate(silence_points):
            if i > 0 and point - silence_points[i - 1] >= 2.0:
                dialogue_breaks.append(point)
        while current_start < video_duration:
            target_end = current_start + self.segment_duration
            if target_end >= video_duration:
                break
            best_point = None
            for break_point in dialogue_breaks:
                if current_start < break_point <= target_end + 15:
                    if best_point is None or abs(break_point - target_end) < abs(best_point - target_end):
                        best_point = break_point
            if best_point is None:
                for point in silence_points:
                    if current_start < point <= target_end + 10:
                        if best_point is None or abs(point - target_end) < abs(best_point - target_end):
                            best_point = point
            if best_point is None:
                best_point = target_end
            segment_length = best_point - current_start
            if segment_length < self.segment_duration * 0.6:
                next_candidates = [p for p in silence_points if p > best_point]
                if next_candidates and next_candidates[0] - current_start <= self.segment_duration * 1.5:
                    best_point = next_candidates[0]
            elif segment_length > self.segment_duration * 1.8:
                mid_point = current_start + self.segment_duration
                for point in silence_points:
                    if mid_point <= point < best_point:
                        best_point = point
                        break
            if best_point <= current_start:
                best_point = target_end
            cut_points.append(best_point)
            current_start = best_point
        return cut_points

    def _resolve_duration(self):
        if self.video_duration > 0:
            return self.video_duration
        return self._get_video_duration()

    def _get_video_duration(self):
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            self.video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        try:
            return float(result.stdout.strip())
        except (ValueError, OSError):
            return 3600

class VideoSplitterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.video_path = ""
        self.output_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        self.video_duration = 0
        self.initUI()

    def initUI(self):
        self.setWindowTitle("视频分割软件")
        self.setGeometry(100, 100, 800, 600)
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, "icon.ico")
        else:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        self.setWindowIcon(QIcon(icon_path))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        upload_group = QGroupBox("视频上传")
        upload_layout = QHBoxLayout()
        self.upload_button = QPushButton("选择视频文件")
        self.upload_button.clicked.connect(self.select_video)
        self.video_label = QLabel("未选择视频文件")
        self.video_label.setWordWrap(True)
        upload_layout.addWidget(self.upload_button)
        upload_layout.addWidget(self.video_label, 1)
        upload_group.setLayout(upload_layout)
        main_layout.addWidget(upload_group)

        info_group = QGroupBox("视频信息")
        info_layout = QFormLayout()
        self.duration_label = QLabel("总时长: 00:00:00")
        self.segment_count_label = QLabel("分割段数: 0")
        info_layout.addRow("总时长:", self.duration_label)
        info_layout.addRow("分割段数:", self.segment_count_label)
        info_group.setLayout(info_layout)
        main_layout.addWidget(info_group)

        param_group = QGroupBox("分割参数")
        param_layout = QFormLayout()
        self.duration_input = QLineEdit("10")
        self.duration_input.textChanged.connect(self.calculate_segments)
        param_layout.addRow("单段时长(分钟):", self.duration_input)

        self.speech_based_checkbox = QCheckBox("基于语音内容分割（智能分割）")
        self.speech_based_checkbox.setToolTip("根据语音停顿、对话间隙和语义完整性自动调整分割点，确保语音段落不被截断")
        param_layout.addRow(self.speech_based_checkbox)

        param_group.setLayout(param_layout)
        main_layout.addWidget(param_group)

        save_group = QGroupBox("保存设置")
        save_layout = QHBoxLayout()
        self.save_path_label = QLabel(self.output_dir)
        self.save_path_label.setWordWrap(True)
        self.save_button = QPushButton("选择保存路径")
        self.save_button.clicked.connect(self.select_output_dir)
        save_layout.addWidget(self.save_path_label, 1)
        save_layout.addWidget(self.save_button)
        save_group.setLayout(save_layout)
        main_layout.addWidget(save_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        main_layout.addWidget(self.log_text)

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("开始分割")
        self.start_button.clicked.connect(self.start_segmentation)
        self.start_button.setEnabled(False)
        self.cancel_button = QPushButton("取消分割")
        self.cancel_button.clicked.connect(self.cancel_segmentation)
        self.cancel_button.setEnabled(False)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

    def select_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", "视频文件 (*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.mpg *.mpeg *.webm *.3gp *.m4v *.ts *.mts *.divx *.xvid)"
        )
        if file_path:
            self.video_path = file_path
            self.video_label.setText(os.path.basename(file_path))
            self.get_video_duration()
            self.calculate_segments()
            self.start_button.setEnabled(True)
            self.log_text.append(f"已选择视频: {file_path}")

    def get_video_duration(self):
        try:
            self.log_text.append(f"开始获取视频信息: {self.video_path}")

            success = self._get_duration_with_ffprobe()
            if success:
                return

            self.log_text.append("尝试使用shell=True执行ffprobe命令")
            success = self._get_duration_with_ffprobe_shell()
            if success:
                return

            self.log_text.append("尝试使用不同的ffprobe参数")
            success = self._get_duration_with_ffprobe_alternative()
            if success:
                return

            self.log_text.append("无法获取视频信息，将使用默认设置")
            self.duration_label.setText("总时长: 未知")

        except Exception as e:
            self.log_text.append(f"获取视频时长失败: {str(e)}")
            import traceback
            self.log_text.append(f"详细错误: {traceback.format_exc()}")

    def _get_duration_with_ffprobe(self):
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-print_format", "json",
                "-show_format",
                self.video_path
            ]
            self.log_text.append(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                shell=False,
                encoding='utf-8',
                errors='ignore'
            )
            self.log_text.append(f"命令返回码: {result.returncode}")

            if result.returncode != 0:
                self.log_text.append(f"ffprobe命令执行失败: {result.stderr}")
                return False

            if not result.stdout:
                self.log_text.append("ffprobe没有返回输出")
                return False

            info = json.loads(result.stdout)
            if "format" in info and "duration" in info["format"]:
                duration = float(info["format"]["duration"])
                self.video_duration = duration
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                seconds = int(duration % 60)
                self.duration_label.setText(f"总时长: {hours:02d}:{minutes:02d}:{seconds:02d}")
                self.log_text.append(f"成功获取视频时长: {hours:02d}:{minutes:02d}:{seconds:02d}")
                return True

        except Exception as e:
            self.log_text.append(f"方法1失败: {str(e)}")
        return False

    def _get_duration_with_ffprobe_shell(self):
        try:
            cmd = f'ffprobe -v error -print_format json -show_format "{self.video_path}"'
            self.log_text.append(f"执行命令: {cmd}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                shell=True,
                encoding='utf-8',
                errors='ignore'
            )
            self.log_text.append(f"命令返回码: {result.returncode}")

            if result.returncode != 0:
                self.log_text.append(f"ffprobe命令执行失败: {result.stderr}")
                return False

            if not result.stdout:
                self.log_text.append("ffprobe没有返回输出")
                return False

            info = json.loads(result.stdout)
            if "format" in info and "duration" in info["format"]:
                duration = float(info["format"]["duration"])
                self.video_duration = duration
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                seconds = int(duration % 60)
                self.duration_label.setText(f"总时长: {hours:02d}:{minutes:02d}:{seconds:02d}")
                self.log_text.append(f"成功获取视频时长: {hours:02d}:{minutes:02d}:{seconds:02d}")
                return True

        except Exception as e:
            self.log_text.append(f"方法2失败: {str(e)}")
        return False

    def _get_duration_with_ffprobe_alternative(self):
        try:
            cmd = [
                "ffprobe",
                "-i", self.video_path,
                "-show_entries", "format=duration",
                "-v", "quiet",
                "-of", "csv=p=0"
            ]
            self.log_text.append(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                shell=False,
                encoding='utf-8',
                errors='ignore'
            )
            self.log_text.append(f"命令返回码: {result.returncode}")

            if result.returncode != 0:
                self.log_text.append(f"ffprobe命令执行失败: {result.stderr}")
                return False

            if not result.stdout:
                self.log_text.append("ffprobe没有返回输出")
                return False

            duration_str = result.stdout.strip()
            if duration_str:
                duration = float(duration_str)
                self.video_duration = duration
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                seconds = int(duration % 60)
                self.duration_label.setText(f"总时长: {hours:02d}:{minutes:02d}:{seconds:02d}")
                self.log_text.append(f"成功获取视频时长: {hours:02d}:{minutes:02d}:{seconds:02d}")
                return True

        except Exception as e:
            self.log_text.append(f"方法3失败: {str(e)}")
        return False

    def calculate_segments(self):
        try:
            segment_duration = float(self.duration_input.text()) * 60
            if segment_duration > 0 and self.video_duration > 0:
                segment_count = max(1, math.ceil(self.video_duration / segment_duration))
                self.segment_count_label.setText(f"分割段数: {segment_count}")
        except ValueError:
            pass

    def select_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择保存路径", self.output_dir
        )
        if dir_path:
            self.output_dir = dir_path
            self.save_path_label.setText(dir_path)
            self.log_text.append(f"已选择保存路径: {dir_path}")

    def start_segmentation(self):
        if not self.video_path:
            self.log_text.append("请先选择视频文件")
            return

        missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
        if missing:
            QMessageBox.warning(
                self, "缺少依赖",
                f"未检测到 {'、'.join(missing)}。\n请先安装 FFmpeg，并将其 bin 目录加入系统 PATH 环境变量后重试。"
            )
            return

        try:
            segment_duration = float(self.duration_input.text()) * 60
            if segment_duration <= 0:
                self.log_text.append("单段时长必须大于0")
                return
        except ValueError:
            self.log_text.append("请输入有效的单段时长")
            return

        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log_text.append("开始分割视频...")
        if self.speech_based_checkbox.isChecked():
            self.log_text.append("使用基于语音内容的智能分割模式...")

        self.worker = VideoSegmentationWorker(
            self.video_path,
            self.output_dir,
            segment_duration,
            video_duration=self.video_duration,
            use_speech_based_segmentation=self.speech_based_checkbox.isChecked()
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.segmentation_finished)
        self.worker.error.connect(self.segmentation_error)
        self.worker.start()

    def cancel_segmentation(self):
        if getattr(self, "worker", None) is not None and self.worker.isRunning():
            self.cancel_button.setEnabled(False)
            self.log_text.append("正在取消分割...")
            self.worker.cancel()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def segmentation_finished(self, message):
        self.log_text.append(message)
        self.progress_bar.setValue(0 if message == "分割已取消" else 100)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if message != "分割已取消":
            QMessageBox.information(self, "分割完成", message)

    def segmentation_error(self, message):
        self.log_text.append(message)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        QMessageBox.critical(self, "分割失败", f"视频分割失败：\n{message}")

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VideoSegmentation.Application")
        except OSError:
            pass
    app = QApplication(sys.argv)
    window = VideoSplitterApp()
    window.show()
    sys.exit(app.exec_())
