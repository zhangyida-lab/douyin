# 简单测试版本


from flask import Flask, request, send_from_directory, jsonify
import os
import subprocess
from flask_cors import CORS


app = Flask(__name__)
CORS(app)  # 启用跨域资源共享

UPLOAD_FOLDER = 'uploads'
HLS_FOLDER = 'hls'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['HLS_FOLDER'] = HLS_FOLDER

# 确保目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(HLS_FOLDER, exist_ok=True)

# 视频转码函数
def transcode_video(input_file, output_dir, output_name):
    # 定义输出目录和文件名
    ts_file_pattern = os.path.join(output_dir, f"{output_name}_%03d.ts")  # .ts 文件的输出模式
    m3u8_file = os.path.join(output_dir, f"{output_name}.m3u8")  # .m3u8 文件路径

    # 构建 FFmpeg 命令
    command = [
        'ffmpeg', '-i', input_file, '-preset', 'ultrafast', '-f', 'hls', '-hls_time', '10',
        '-hls_list_size', '0', '-hls_segment_filename', ts_file_pattern, m3u8_file
    ]
    
    try:
        # 捕获输出日志
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print(result.stdout)  # 打印标准输出
        print(result.stderr)  # 打印错误输出
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg failed with error: {e.stderr}")
    
    return m3u8_file  # 返回 .m3u8 文件路径


# 上传视频路由
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file:
        filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filename)

        # 进行视频转码并生成HLS流
        hls_playlist = transcode_video(filename, HLS_FOLDER, file.filename.split('.')[0])
        
        return jsonify({
            'message': 'File uploaded and processed successfully',
            'hls_playlist': f'http://localhost:5000/hls/{os.path.basename(hls_playlist)}'
        }), 200

# 提供HLS流媒体文件
@app.route('/hls/<path:filename>')
def stream_video(filename):
    return send_from_directory(app.config['HLS_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)
