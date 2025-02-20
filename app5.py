from flask import Flask, request, send_from_directory, jsonify
import os
import subprocess
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import uuid
import random
import sqlite3
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import os

app = Flask(__name__)
CORS(app)  # 启用跨域资源共享

# 配置 SQLite 数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///videos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['HLS_FOLDER'] = 'hls'

db = SQLAlchemy(app)

# 确保目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['HLS_FOLDER'], exist_ok=True)

# 用户模型
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    
    # 用户和视频的多对多关系
    videos = db.relationship('Video', secondary='user_video_history', backref=db.backref('users', lazy=True))
    
    def __repr__(self):
        return f'<User {self.username}>'

# 用户视频历史模型（用户观看和点赞的视频）
class UserVideoHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id', ondelete='CASCADE'), nullable=False)
    watched = db.Column(db.Boolean, default=False)  # 用户是否观看过
    liked = db.Column(db.Boolean, default=False)    # 用户是否点赞了视频

# 视频模型
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(120), nullable=False)
    hls_url = db.Column(db.String(500), nullable=False)
    likes = db.Column(db.Integer, default=0)
    tags = db.Column(db.String(500))  # 用逗号分隔的标签字段
    duration = db.Column(db.Integer)  # 视频时长（秒）
    category = db.Column(db.String(50))  # 视频类别（例如电影、短片等）

    def __repr__(self):
        return f'<Video {self.filename}>'

# 创建数据库表
with app.app_context():
    db.create_all()

# 确保数据库中有默认用户
def create_default_user():
    default_user = User.query.filter_by(username='test_user').first()
    if not default_user:
        default_user = User(username='test_user', email='test_user@example.com')
        db.session.add(default_user)
        db.session.commit()
    
    return default_user


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


# 计算视频的特征矩阵
def get_video_features(videos):
    # 获取视频标签作为文本特征
    video_tags = [video.tags for video in videos]  # 使用标签字段作为特征
    vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(video_tags)
    return tfidf_matrix

# 根据视频ID获取相似视频
def get_similar_videos(video_id, tfidf_matrix, videos):
    # 计算指定视频与所有视频的相似度
    cosine_sim = cosine_similarity(tfidf_matrix[video_id], tfidf_matrix)
    similar_indices = cosine_sim.argsort()[0][-6:-1]  # 返回最相似的前5个视频（排除自己）
    
    similar_videos = [videos[i] for i in similar_indices]
    return similar_videos

# 获取用户观看历史
def get_user_history(user_id):
    # 获取用户观看过的视频（如果已经观看）
    watched_videos = db.session.query(Video).join(UserVideoHistory).filter(
        UserVideoHistory.user_id == user_id, UserVideoHistory.watched == True
    ).all()
    return watched_videos

# 获取视频推荐列表
@app.route('/recommend/<int:user_id>', methods=['GET'])
def recommend_videos(user_id):
    # 获取用户的观看历史
    user_history = get_user_history(user_id)
    videos = Video.query.all()  # 获取所有视频
    
    # 获取视频内容特征
    tfidf_matrix = get_video_features(videos)
    
    recommended_videos = []
    
    # 获取每个视频的相似视频
    for video in user_history:
        similar_videos = get_similar_videos(video.id, tfidf_matrix, videos)
        recommended_videos.extend(similar_videos)
    
    # 去重，返回推荐的视频
    recommended_videos = list({v.id: v for v in recommended_videos}.values())
    
    # 生成视频推荐列表
    video_list = [{
        'id': video.id,
        'filename': video.filename,
        'hls_url': video.hls_url,
        'likes': video.likes
    } for video in recommended_videos]

    return jsonify(video_list), 200

# 上传视频
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


    # 生成HLS URL（此处简化，只返回文件路径）
    hls_url = f"http://localhost:5000/hls/{unique_filename}"
    
    # 需要从请求中获取其他视频信息（例如标签、时长等）
    new_video = Video(
        filename=file.filename,
        hls_url=f'http://localhost:5000/hls/{os.path.basename(hls_playlist)}',
        tags="action, adventure",  # 示例标签
        duration=300,  # 示例时长（秒）
        category="movie"  # 示例类别
    )

    db.session.add(new_video)
    db.session.commit()

    return jsonify({'message': 'File uploaded successfully', 'hls_url': hls_url}), 200

# 观看视频
@app.route('/watch/<int:user_id>/<int:video_id>', methods=['POST'])
def watch_video(user_id, video_id):
    user = User.query.get_or_404(user_id)
    video = Video.query.get_or_404(video_id)
    
    # 检查是否已经记录该用户的视频观看历史
    history = UserVideoHistory.query.filter_by(user_id=user_id, video_id=video_id).first()
    if not history:
        # 如果没有记录，则创建新记录
        history = UserVideoHistory(user_id=user_id, video_id=video_id, watched=True)
        db.session.add(history)
    else:
        # 更新已观看状态
        history.watched = True
    
    db.session.commit()
    return jsonify({'message': f'User {user.username} watched video {video.filename}'}), 200

# 点赞视频
@app.route('/like/<int:user_id>/<int:video_id>', methods=['POST'])
def like_video(user_id, video_id):
    user = User.query.get_or_404(user_id)
    video = Video.query.get_or_404(video_id)
    
    # 检查是否已经点赞
    history = UserVideoHistory.query.filter_by(user_id=user_id, video_id=video_id).first()
    if not history:
        # 如果没有记录，则创建新记录
        history = UserVideoHistory(user_id=user_id, video_id=video_id, liked=True)
        db.session.add(history)
    else:
        # 更新点赞状态
        history.liked = True
    
    # 更新视频的点赞数
    video.likes += 1
    db.session.commit()
    
    return jsonify({'message': f'User {user.username} liked video {video.filename}'}), 200

# 提供HLS流媒体文件
@app.route('/hls/<path:filename>')
def stream_video(filename):
    return send_from_directory(app.config['HLS_FOLDER'], filename)

# 获取用户历史记录
@app.route('/history/<int:user_id>', methods=['GET'])
def get_user_history(user_id):
    user = User.query.get_or_404(user_id)
    
    # 获取用户观看过的视频（如果已经观看）
    watched_videos = db.session.query(Video).join(UserVideoHistory).filter(
        UserVideoHistory.user_id == user_id, UserVideoHistory.watched == True
    ).all()
    
    # 返回视频列表
    video_list = [{
        'id': video.id,
        'filename': video.filename,
        'hls_url': video.hls_url,
        'likes': video.likes
    } for video in watched_videos]
    
    return jsonify(video_list), 200

@app.route('/api/videos', methods=['GET'])
def get_sorted_videos():
    # 从数据库中按点赞数降序排列并获取前20个视频
    videos = Video.query.order_by(Video.likes.desc()).limit(30).all()

    # 生成视频列表
    video_list = [{
        'id': video.id,
        'filename': video.filename,
        'hls_url': video.hls_url,
        'likes': video.likes
    } for video in videos]

    return jsonify(video_list)

# 初始化应用
@app.before_request
def initialize_app():
    default_user = create_default_user()
    # 如果需要，可以在这里为默认用户添加一些观看历史
    # 例如，给默认用户添加一个观看记录
    video = Video.query.first()
    if video:
        history = UserVideoHistory(user_id=default_user.id, video_id=video.id, watched=True)
        db.session.add(history)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)