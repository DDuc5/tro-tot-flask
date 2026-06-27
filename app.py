from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import firebase_admin 
from firebase_admin import credentials, firestore, auth
import os
import json

# --- THAY THẾ ĐOẠN KHỞI TẠO FIREBASE CŨ BẰNG ĐOẠN NÀY ---
firebase_credentials = os.environ.get('FIREBASE_CREDENTIALS')

if not firebase_admin._apps:
    if firebase_credentials:
        # Nếu đang chạy trên Server (Render), đọc Key từ Biến môi trường
        cred_dict = json.loads(firebase_credentials)
        cred = credentials.Certificate(cred_dict)
    else:
        # Nếu đang chạy ở máy tính (Local), đọc từ file JSON
        cred = credentials.Certificate("serviceAccountKey.json")
    
    firebase_admin.initialize_app(cred)

db = firestore.client()

@app.route('/')
def home():
    user_info = session.get('user')
    
    # 1. Kéo toàn bộ bài đăng từ collection 'posts' trên Firestore, sắp xếp mới nhất lên đầu
    posts_ref = db.collection('posts').order_by('created_at', direction=firestore.Query.DESCENDING)
    posts = []
    try:
        for doc in posts_ref.stream():
            post_data = doc.to_dict()
            post_data['id'] = doc.id # Lưu lại ID của bài viết
            posts.append(post_data)
    except Exception as e:
        print("Chưa có dữ liệu bài đăng hoặc lỗi:", e)

    # 2. Truyền danh sách 'posts' ra ngoài giao diện index.html
    return render_template('index.html', user=user_info, posts=posts)


@app.route('/post', methods=['GET', 'POST'])
def post_listing():
    user_info = session.get('user')
    if not user_info:
        return redirect(url_for('login_page'))
        
    if request.method == 'POST':
        try:
            # Lấy dữ liệu Text từ Form do JavaScript gửi về
            title = request.form.get('title', 'Chưa có tiêu đề')
            price = request.form.get('price', 0)
            area = request.form.get('area', 0)
            room_type = request.form.get('room_type', 'Phòng trọ')
            street = request.form.get('street', 'Chưa rõ địa chỉ')
            package_type = request.form.get('package_type', 'Cơ bản')
            duration_days = request.form.get('duration_days', 7)
            
            # --- BỔ SUNG 2 DÒNG NÀY ĐỂ LẤY MÔ TẢ VÀ NỘI THẤT ---
            description = request.form.get('description', 'Chưa có mô tả')
            furnishing = request.form.get('furnishing', 'Trống')

            default_image = "https://via.placeholder.com/400x300/00acc1/ffffff?text=Tin+Dang+Moi"

            # Đóng gói dữ liệu
            new_post = {
                'title': title,
                'price': int(price) if price else 0,
                'area': int(area) if area else 0,
                'room_type': room_type,
                'address': street,
                'image_url': default_image,
                'author_uid': user_info.get('uid'),
                'author_name': user_info.get('display_name'),
                'package': package_type,
                'duration': int(duration_days),
                
                # --- BỔ SUNG 2 DÒNG NÀY ĐỂ LƯU VÀO FIREBASE ---
                'description': description,
                'furnishing': furnishing,
                
                'created_at': firestore.SERVER_TIMESTAMP,
                'status': 'active'
            }
            
            db.collection('posts').add(new_post)
            return jsonify({"status": "success", "message": "Đã lưu tin đăng vào hệ thống!"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})
    return render_template('post.html', user=user_info)

@app.route('/login', methods=['GET'])
def login_page():
    if 'user' in session:
        return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/register', methods=['GET'])
def register_page():
    if 'user' in session:
        return redirect(url_for('home'))
    return render_template('register.html')

@app.route('/api/set-session', methods=['POST'])
def set_session():
    """API nhận ID Token từ Frontend sau khi Firebase Auth đăng nhập thành công"""
    data = request.json
    id_token = data.get('idToken')
    
    try:
        # Thêm clock_skew_seconds=60 để sửa lỗi lệch múi giờ giữa máy tính và Google
        decoded_token = auth.verify_id_token(id_token, clock_skew_seconds=60)
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        
        user_doc = db.collection('users').document(uid).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        
        session['user'] = {
            'uid': uid,
            'email': email,
            'display_name': user_data.get('display_name', 'Thành viên'),
            'phone': user_data.get('phone', '')
        }
        
        return jsonify({"status": "success", "message": "Đã thiết lập phiên đăng nhập thành công"}), 200
    except Exception as e:
        print(f"\n[LỖI SERVER] Xác thực Token thất bại: {str(e)}\n")
        return jsonify({"status": "error", "message": str(e)}), 401

@app.route('/api/create-user-profile', methods=['POST'])
def create_user_profile():
    """API lưu trữ thông tin bổ sung của User vào Firestore khi Đăng ký thành công"""
    data = request.json
    uid = data.get('uid')
    email = data.get('email')
    display_name = data.get('display_name')
    phone = data.get('phone')
    
    try:
        # Lưu vào collection 'users' với ID tài liệu chính là UID của Firebase Auth
        db.collection('users').document(uid).set({
            'email': email,
            'display_name': display_name,
            'phone': phone,
            'role': 'member', # Mặc định là thành viên thông thường
            'created_at': firestore.SERVER_TIMESTAMP
        })
        return jsonify({"status": "success", "message": "Đã lưu hồ sơ người dùng"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))
@app.route('/chat')
def chat_page():
    user_info = session.get('user')
    if not user_info:
        return redirect(url_for('login_page'))
    return render_template('chat.html', user=user_info)

@app.route('/manage-posts')
def manage_posts_page():
    user_info = session.get('user')
    if not user_info:
        return redirect(url_for('login_page'))
    
    # Kéo các bài viết do chính user này đăng từ Firebase
    my_posts = []
    try:
        docs = db.collection('posts').where('author_uid', '==', user_info['uid']).stream()
        for doc in docs:
            p = doc.to_dict()
            p['id'] = doc.id
            my_posts.append(p)
        
        # Sắp xếp bài mới nhất lên đầu (bằng Python để tránh lỗi Index của Firebase)
        my_posts.sort(key=lambda x: x.get('created_at', 0), reverse=True)
    except Exception as e:
        print("Lỗi tải bài viết cá nhân:", e)

    return render_template('manage_posts.html', user=user_info, posts=my_posts)

# --- THÊM ROUTE MỚI: XEM CHI TIẾT 1 BÀI VIẾT ---
@app.route('/post/<post_id>')
def view_post(post_id):
    user_info = session.get('user')
    try:
        doc = db.collection('posts').document(post_id).get()
        if doc.exists:
            post_data = doc.to_dict()
            post_data['id'] = doc.id
            return render_template('post_detail.html', post=post_data, user=user_info)
        else:
            return "Không tìm thấy bài viết này", 404
    except Exception as e:
        return f"Lỗi: {str(e)}", 500
if __name__ == '__main__':
    app.run(debug=True, port=5000)