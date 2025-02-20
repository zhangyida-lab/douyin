import SwiftUI
import AVKit

struct Video: Identifiable, Decodable {
    var id: Int
    var filename: String
    var hls_url: String
    var likes: Int
}

class VideoViewModel: ObservableObject {
    @Published var videos = [Video]()
    @Published var currentIndex = 0
    @Published var isLoading = true
    
    // 获取视频列表
    func fetchVideos() {
        guard let url = URL(string: "http://192.168.0.21:5000/api/videos") else { return }
        
        DispatchQueue.main.async {
            self.isLoading = true
        }
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            if let error = error {
                DispatchQueue.main.async {
                    self.isLoading = false
                }
                print("Error fetching videos: \(error.localizedDescription)")
                return
            }
            
            guard let data = data else {
                DispatchQueue.main.async {
                    self.isLoading = false
                }
                print("No data received.")
                return
            }
            
            do {
                let decodedVideos = try JSONDecoder().decode([Video].self, from: data)
                
                // 替换每个视频的 hls_url 中的 localhost 为 192.168.0.21
                let updatedVideos = decodedVideos.map { video in
                    var updatedVideo = video
                    updatedVideo.hls_url = updatedVideo.hls_url.replacingOccurrences(of: "localhost", with: "192.168.0.21")
                    return updatedVideo
                }
                
                DispatchQueue.main.async {
                    self.videos = updatedVideos
                    self.isLoading = false
                }
            } catch {
                DispatchQueue.main.async {
                    self.isLoading = false
                }
                print("Error decoding video data: \(error)")
            }
        }.resume()
    }
    
    // 点赞视频
    func likeVideo(videoId: Int) {
        guard let url = URL(string: "http://192.168.0.21:5000/like/\(videoId)") else { return }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if error == nil {
                DispatchQueue.main.async {
                    if let index = self.videos.firstIndex(where: { $0.id == videoId }) {
                        self.videos[index].likes += 1
                    }
                }
            }
        }.resume()
    }
    
    // 更新当前视频索引
    func updateCurrentIndex(isUpSwipe: Bool) {
        if isUpSwipe {
            currentIndex = max(0, currentIndex - 1)  // 上滑，前一个视频
        } else {
            currentIndex = min(videos.count - 1, currentIndex + 1)  // 下滑，后一个视频
        }
    }
}

struct VideoPlayerWithGestures: View {
    @StateObject private var viewModel = VideoViewModel()
    
    var body: some View {
        ZStack {
            if viewModel.isLoading {
                ProgressView("Loading videos...")
                    .progressViewStyle(CircularProgressViewStyle())
            } else {
                GeometryReader { geometry in
                    VStack {
                        if !viewModel.videos.isEmpty {
                            let video = viewModel.videos[viewModel.currentIndex]
                            VideoPlayer(player: AVPlayer(url: URL(string: video.hls_url)!))
                                .onAppear {
                                    print("Playing video: \(video.filename)")
                                }
                                .onDisappear {
                                    print("Stopped video: \(video.filename)")
                                }
                                .frame(width: geometry.size.width, height: geometry.size.height * 0.75)
                            
                            // 显示视频标题和点赞按钮
                            VStack(alignment: .leading) {
                                Text(video.filename)
                                    .font(.headline)
                                    .foregroundColor(.white)
                                    .padding(.bottom, 4)
                                HStack {
                                    Text("Likes: \(video.likes)")
                                        .foregroundColor(.white)
                                    Spacer()
                                    Button(action: {
                                        viewModel.likeVideo(videoId: video.id)
                                    }) {
                                        Image(systemName: "heart.fill")
                                            .foregroundColor(.red)
                                            .padding(8)
                                    }
                                }
                            }
                            .padding()
                            .background(Color.black.opacity(0.7))
                            .cornerRadius(10)
                        }
                    }
                    .gesture(
                        DragGesture()
                            .onEnded { value in
                                if value.translation.height > 50 {  // 下划切换视频
                                    viewModel.updateCurrentIndex(isUpSwipe: false)
                                } else if value.translation.height < -50 {  // 上划切换视频
                                    viewModel.updateCurrentIndex(isUpSwipe: true)
                                }
                            }
                    )
                }
                .padding()
                .edgesIgnoringSafeArea(.all)
            }
        }
        .onAppear {
            viewModel.fetchVideos()
        }
    }
}

struct ContentView: View {
    var body: some View {
        VideoPlayerWithGestures()
            .statusBar(hidden: true)
    }
}

@main
struct VideoApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
