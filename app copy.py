from flask import Flask, request, send_from_directory, jsonify
import os
import subprocess
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import uuid
import random
import mysql.connector

app = Flask(__name__)
CORS(app)  # 启用跨域资源共享

# 配置 MySQL 数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:password@localhost/videos_db'  # MySQL数据库连接
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['HLS_FOLDER'] = 'hls'

db = SQLAlchemy(app)

# 确保目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['HLS_FOLDER'], exist_ok=True)

# 创建视频信息模型
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(120), nullable=False)
    hls_url = db.Column(db.String(500), nullable=False)
    likes = db.Column(db.Integer, default=0)
    category = db.Column(db.String(50), nullable=True)  # 新增类型字段

    def __repr__(self):
        return f'<Video {self.filename}>'

# 创建数据库表
with app.app_context():
    db.create_all()

# 视频转码函数
def transcode_video(input_file, output_dir, output_name):
    ts_file_pattern = os.path.join(output_dir, f"{output_name}_%03d.ts")  # .ts 文件的输出模式
    m3u8_file = os.path.join(output_dir, f"{output_name}.m3u8")  # .m3u8 文件路径

    command = [
        'ffmpeg', '-i', input_file, '-preset', 'ultrafast', '-f', 'hls', '-hls_time', '10',
        '-hls_list_size', '0', '-hls_segment_filename', ts_file_pattern, m3u8_file
    ]
    
    try:
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
    
    # 生成唯一文件名
    unique_filename = str(uuid.uuid4()) + os.path.splitext(file.filename)[1]
    filename = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    file.save(filename)

    # 进行视频转码并生成HLS流
    hls_playlist = transcode_video(filename, app.config['HLS_FOLDER'], unique_filename.split('.')[0])

    # 保存视频信息到数据库
    new_video = Video(
        filename=file.filename,
        hls_url=f'http://localhost:5000/hls/{os.path.basename(hls_playlist)}'
    )
    db.session.add(new_video)
    db.session.commit()

    return jsonify({
        'message': 'File uploaded and processed successfully',
        'hls_playlist': f'http://localhost:5000/hls/{os.path.basename(hls_playlist)}'
    }), 200

# 获取视频推荐列表
@app.route('/videos', methods=['GET'])
def get_videos():
    videos = Video.query.all()
    video_list = [{
        'id': video.id,
        'filename': video.filename,
        'hls_url': video.hls_url,
        'likes': video.likes
    } for video in videos]
    
    return jsonify(video_list), 200

# 点赞视频
@app.route('/like/<int:video_id>', methods=['POST'])
def like_video(video_id):
    video = Video.query.get_or_404(video_id)
    video.likes += 1
    db.session.commit()
    return jsonify({'message': 'Video liked successfully'}), 200

# 提供HLS流媒体文件
@app.route('/hls/<path:filename>')
def stream_video(filename):
    return send_from_directory(app.config['HLS_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)
