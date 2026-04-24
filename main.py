import sys
import os
import subprocess
import json
import tempfile
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog, QProgressBar,
    QTextEdit, QGroupBox, QFormLayout, QComboBox, QMessageBox, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon

class VideoSegmentationWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, video_path, output_dir, segment_duration, use_speech_based_segmentation=False):
        super().__init__()
        self.video_path = video_path
        self.output_dir = output_dir
        self.segment_duration = segment_duration
        self.use_speech_based_segmentation = use_speech_based_segmentation

    def run(self):
        try:
            if self.use_speech_based_segmentation:
                self._segment_based_on_speech()
            else:
                self._segment_based_on_time()
        except Exception as e:
            self.error.emit(f"错误: {str(e)}")

    def _segment_based_on_time(self):
        gpu_available = self._check_gpu_available()
        try:
            base_name, ext = os.path.splitext(os.path.basename(self.video_path))
            output_pattern = os.path.join(self.output_dir, f"{base_name}_part_%03d{ext}")
            
            cmd = [
                "ffmpeg",
                "-y",
                "-i", self.video_path,
                "-c", "copy",
                "-map", "0:v",
                "-map", "0:a",
                "-segment_time", str(self.segment_duration),
                "-f", "segment",
                "-reset_timestamps", "1",
                output_pattern
            ]
            
            error_output = []
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                universal_newlines=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            while True:
                try:
                    output = process.stderr.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        error_output.append(output)
                        if "time=" in output:
                            time_str = output.split("time=")[1].split(" ")[0]
                            h, m, s = map(float, time_str.split(":"))
                            current_time = h * 3600 + m * 60 + s
                            progress = int((current_time / (self.segment_duration * 10)) * 100)
                            if progress > 100:
                                progress = 100
                            self.progress.emit(progress)
                except UnicodeDecodeError:
                    pass
            
            if process.returncode == 0:
                self.finished.emit("视频分割完成！")
            else:
                error_message = ''.join(error_output)
                if not error_message:
                    error_message = "未知错误"
                self.error.emit(f"分割失败: {error_message}")
        except Exception as e:
            self.error.emit(f"错误: {str(e)}")

    def _segment_based_on_speech(self):
        try:
            self.progress.emit(5)
            
            temp_audio = tempfile.mktemp(suffix=".wav")
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
            
            result = subprocess.run(extract_cmd, capture_output=True, encoding='utf-8', errors='ignore')
            if result.returncode != 0:
                raise Exception(f"音频提取失败: {result.stderr}")
            
            self.progress.emit(15)
            
            audio_analysis = self._analyze_audio(temp_audio)
            silence_points = audio_analysis['silence_points']
            speech_segments = audio_analysis['speech_segments']
            
            self.progress.emit(40)
            
            segment_points = self._determine_smart_segment_points(
                silence_points, 
                speech_segments,
                audio_analysis
            )
            self.progress.emit(55)
            
            base_name, ext = os.path.splitext(os.path.basename(self.video_path))
            
            for i, (start, end) in enumerate(segment_points):
                output_file = os.path.join(self.output_dir, f"{base_name}_part_{i:03d}{ext}")
                segment_cmd = self._build_segment_command(
                    self.video_path,
                    output_file,
                    start,
                    end
                )
                subprocess.run(segment_cmd, capture_output=True, check=True, encoding='utf-8', errors='ignore')
                
                segment_progress = 55 + int((i + 1) / len(segment_points) * 40)
                if segment_progress > 95:
                    segment_progress = 95
                self.progress.emit(segment_progress)
            
            if os.path.exists(temp_audio):
                os.remove(temp_audio)
            
            self.progress.emit(100)
            self.finished.emit("基于语音内容的智能视频分割完成！")
        except Exception as e:
            self.error.emit(f"基于语音内容分割失败: {str(e)}")

    def _check_gpu_available(self):
        try:
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                encoding='utf-8',
                errors='ignore'
            )
            return result.returncode == 0
        except:
            return False

    def _build_segment_command(self, input_file, output_file, start, end):
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(start),
            "-i", input_file,
            "-to", str(end - start),
            "-c:v", "copy",
            "-c:a", "copy",
            output_file
        ]
        return cmd

    def _analyze_audio(self, audio_file):
        result = {
            'silence_points': [],
            'speech_segments': [],
            'energy_profile': []
        }
        
        energy_points = self._analyze_audio_energy(audio_file)
        result['energy_profile'] = energy_points
        
        silence_points = self._detect_silence_improved(audio_file)
        result['silence_points'] = silence_points
        
        speech_segments = self._analyze_speech_segments(silence_points, energy_points)
        result['speech_segments'] = speech_segments
        
        return result

    def _analyze_audio_energy(self, audio_file):
        cmd = [
            "ffmpeg",
            "-i", audio_file,
            "-af", "astats=metadata=1:reset=1",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        energy_points = []
        lines = result.stderr.split('\n')
        
        for line in lines:
            if "RMS level" in line:
                try:
                    parts = line.split("RMS level dB: ")
                    if len(parts) > 1:
                        rms_db = float(parts[1].split()[0])
                        energy_points.append(rms_db)
                except:
                    pass
        
        return energy_points

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
        lines = result.stderr.split('\n')
        
        for line in lines:
            if "silence_end" in line:
                try:
                    end = float(line.split('silence_end: ')[1].split(' ')[0])
                    silence_points.append(end)
                except:
                    pass
        
        return silence_points

    def _analyze_speech_segments(self, silence_points, energy_points):
        speech_segments = []
        
        silence_points = [0] + sorted(silence_points) + [float('inf')]
        
        for i in range(len(silence_points) - 1):
            start = silence_points[i]
            end = silence_points[i + 1]
            
            if end != float('inf') and start != 0:
                speech_segments.append({
                    'start': start,
                    'end': end,
                    'duration': end - start
                })
        
        return speech_segments

    def _determine_smart_segment_points(self, silence_points, speech_segments, audio_analysis):
        segment_points = []
        current_start = 0
        video_duration = self._get_video_duration()
        
        dialogue_breaks = []
        for i, point in enumerate(silence_points):
            if i > 0:
                gap = point - silence_points[i-1]
                if gap >= 2.0:
                    dialogue_breaks.append(point)
        
        while current_start < video_duration:
            target_end = current_start + self.segment_duration
            
            if target_end >= video_duration:
                segment_points.append((current_start, video_duration))
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
                if next_candidates:
                    next_point = next_candidates[0]
                    if next_point - current_start <= self.segment_duration * 1.5:
                        best_point = next_point
            elif segment_length > self.segment_duration * 1.8:
                mid_point = current_start + self.segment_duration
                for point in silence_points:
                    if mid_point <= point < best_point:
                        best_point = point
                        break
            
            segment_points.append((current_start, best_point))
            current_start = best_point
        
        return segment_points

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
        except:
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

        self.start_button = QPushButton("开始分割")
        self.start_button.clicked.connect(self.start_segmentation)
        self.start_button.setEnabled(False)
        main_layout.addWidget(self.start_button)

    def select_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", "视频文件 (*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.mpg *.mpeg *.webm *.3gp *.m4v *.ts *.mts *.wmv *.divx *.xvid)"
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
            if self.video_duration > 0:
                segment_count = int(self.video_duration / segment_duration) + 1
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

        try:
            segment_duration = float(self.duration_input.text()) * 60
            if segment_duration <= 0:
                self.log_text.append("单段时长必须大于0")
                return
        except ValueError:
            self.log_text.append("请输入有效的单段时长")
            return

        self.start_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_text.append("开始分割视频...")
        if self.speech_based_checkbox.isChecked():
            self.log_text.append("使用基于语音内容的智能分割模式...")

        self.worker = VideoSegmentationWorker(
            self.video_path, 
            self.output_dir, 
            segment_duration,
            use_speech_based_segmentation=self.speech_based_checkbox.isChecked()
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.segmentation_finished)
        self.worker.error.connect(self.segmentation_error)
        self.worker.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def segmentation_finished(self, message):
        self.log_text.append(message)
        self.progress_bar.setValue(100)
        self.start_button.setEnabled(True)
        QMessageBox.information(self, "分割完成", "视频分割已成功完成！")

    def segmentation_error(self, message):
        self.log_text.append(message)
        self.start_button.setEnabled(True)
        QMessageBox.critical(self, "分割失败", f"视频分割失败：\n{message}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoSplitterApp()
    window.show()
    sys.exit(app.exec_())