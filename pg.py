import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder='.')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-spetter')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///spetter.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# 🗂️ 完璧なデータベースモデル定義
# ==========================================

# フォロー関係の中間テーブル（相互フォローでフレンド成立）
followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    bio_memo = db.Column(db.Text, default='') # アカウントメモ
    icon_num = db.Column(db.Integer, default=1) # アイコン設定（1〜10のテーマカラー）
    is_admin = db.Column(db.Boolean, default=False)
    is_official = db.Column(db.Boolean, default=False)

    # 50個以上の細かい設定を1文字ずつ保存するテキスト（例: "1011000..." ）
    # これによりJavaScriptなしでも50以上の設定項目を完全にPythonで管理・記憶できます
    settings_data = db.Column(db.String(100), default='0' * 60) 

    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic'
    )

    # 相互フォロー（フレンド）判定関数
    def is_friend(self, other_user):
        if not other_user: return False
        return self.followed.filter(followers.c.followed_id == other_user.id).count() > 0 and \
               other_user.followed.filter(followers.c.followed_id == self.id).count() > 0
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    reply_to = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True) # 返信機能用
    mention_to = db.Column(db.String(80), nullable=True) # ○○○さん宛機能用
    is_global = db.Column(db.Boolean, default=True)
    
    user = db.relationship('User', backref=db.backref('messages', lazy=True))

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

class InboxItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # 受信箱の持ち主
    sender_name = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # 通知を受け取る人
    sender_name = db.Column(db.String(80), nullable=False)
    message_id = db.Column(db.Integer, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

# 初期起動時にデータベースとテスト用管理者を作るブロック
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin_user = User(
            username='admin', 
            email='admin@spetter.com', 
            password_hash=generate_password_hash('admin123'),
            is_admin=True, is_official=True
        )
        db.session.add(admin_user)
        db.session.commit()
# ==========================================
# ⚙️ 画面表示・アカウント管理の処理（ルート）
# ==========================================

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    current_user = User.query.get(session['user_id'])
    
    # 未読のフレンド通知を自動検知して取得（表示したら既読にする）
    unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).all()
    for note in unread_notifications:
        note.is_read = True
    db.session.commit()
    
    messages = Message.query.filter_by(is_global=True).order_by(Message.timestamp.desc()).all()
    
    # 黒い起動イントロをログインごとに1回だけ見せる処理
    show_intro = False
    if 'intro_shown' not in session:
        show_intro = True
        session['intro_shown'] = True
    
    return render_template(
        'in.html', 
        user=current_user, 
        messages=messages, 
        notifications=unread_notifications,
        show_intro=show_intro
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash('ユーザー名またはメールアドレスが既に存在します。')
            return redirect(url_for('register'))
            
        hashed_pw = generate_password_hash(password)
        new_user = User(username=username, email=email, password_hash=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash('アカウント作成完了！ログインしてください。')
        return redirect(url_for('login'))
        
    return render_template('in.html', mode='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session.pop('intro_shown', None) # イントロをリセット
            return redirect(url_for('index'))
            
        flash('ユーザー名またはパスワードが間違っています。')
    return render_template('in.html', mode='login')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form['email']
        new_password = request.form['new_password']
        user = User.query.filter_by(email=email).first()
        if user:
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash('パスワードをリセットしました！ログインしてください。')
            return redirect(url_for('login'))
        flash('メールアドレスが見つかりません。')
    return render_template('in.html', mode='reset_password')
# メッセージ送信（フレンド通知＆宛先による受信箱自動転送機能付き）
@app.route('/post_message', methods=['POST'])
def post_message():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    current_user = User.query.get(session['user_id'])
    content = request.form.get('content')
    reply_to = request.form.get('reply_to')
    mention_to = request.form.get('mention_to') # ○○さん宛
    
    if content:
        # 1. グローバルタイムライン用にメッセージを保存
        msg = Message(
            user_id=current_user.id, 
            content=content,
            reply_to=reply_to if reply_to else None,
            mention_to=mention_to if mention_to else None
        )
        db.session.add(msg)
        db.session.flush() # IDを確定

        # 2. 受信箱機能：もし特定の宛先（○○さん宛）が指定されていたら、相手の受信箱に自動転送
        if mention_to:
            target_user = User.query.filter_by(username=mention_to).first()
            if target_user:
                inbox_item = InboxItem(
                    user_id=target_user.id,
                    sender_name=current_user.username,
                    title="あなた宛ての新しいポスト",
                    body=content
                )
                db.session.add(inbox_item)

        # 3. 通知機能：自分をフォローしているフレンド全員へ通知を作成
        for follower in current_user.followers:
            if current_user.is_friend(follower):
                new_note = Notification(
                    user_id=follower.id,
                    sender_name=current_user.username,
                    message_id=msg.id
                )
                db.session.add(new_note)
        
        db.session.commit()
    return redirect(url_for('index'))

# 1対1の秘密のプライベートチャット処理
@app.route('/chat/<username>', methods=['GET', 'POST'])
def private_chat(username):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    current_user = User.query.get(session['user_id'])
    chat_partner = User.query.filter_by(username=username).first_or_404()
    
    if request.method == 'POST':
        content = request.form.get('content')
        if content:
            new_chat = ChatMessage(sender_id=current_user.id, receiver_id=chat_partner.id, content=content)
            db.session.add(new_chat)
            db.session.commit()
            return redirect(url_for('private_chat', username=username))
            
    chat_messages = ChatMessage.query.filter(
        ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id == chat_partner.id)) |
        ((ChatMessage.sender_id == chat_partner.id) & (ChatMessage.receiver_id == current_user.id))
    ).order_by(ChatMessage.timestamp.asc()).all()
    
    return render_template('in.html', mode='chat', user=current_user, partner=chat_partner, chat_messages=chat_messages)

# フォロー・フォロー解除処理
@app.route('/follow/<username>')
def follow(username):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    current_user = User.query.get(session['user_id'])
    user_to_follow = User.query.filter_by(username=username).first_or_404()
    
    if current_user != user_to_follow:
        if user_to_follow in current_user.followed:
            current_user.followed.remove(user_to_follow)
            flash(f'{username} のフォローを解除しました。')
        else:
            current_user.followed.append(user_to_follow)
            flash(f'{username} をフォローしました！')
        db.session.commit()
    return redirect(url_for('index'))

# 受信箱の画面表示
@app.route('/inbox')
def inbox():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    current_user = User.query.get(session['user_id'])
    items = InboxItem.query.filter_by(user_id=current_user.id).order_by(InboxItem.timestamp.desc()).all()
    return render_template('in.html', mode='inbox', user=current_user, inbox_items=items)

# プロフィールメモとアイコンの一括更新
@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    current_user = User.query.get(session['user_id'])
    current_user.bio_memo = request.form.get('bio_memo', '')
    current_user.icon_num = int(request.form.get('icon_num', 1))
    db.session.commit()
    flash('プロフィール設定を更新しました！')
    return redirect(url_for('index'))

# 🎛️ 50以上の詳細設定を一括でセーブする処理
@app.route('/save_settings', methods=['POST'])
def save_settings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    current_user = User.query.get(session['user_id'])
    
    settings_list = []
    for i in range(55):
        val = request.form.get(f'set_{i}', '0')
        settings_list.append('1' if val == '1' else '0')
        
    current_user.settings_data = "".join(settings_list)
    db.session.commit()
    flash('50以上の詳細設定をすべて保存しました！')
    return redirect(url_for('index'))

# 🛠️ 特別URLによる隠し管理者画面機能
@app.route('/admin/menu')
def admin_menu():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    current_user = User.query.get(session['user_id'])
    if not current_user.is_admin:
        flash('この特別URLは、管理者アカウント以外は立ち入り禁止です！')
        return redirect(url_for('index'))
    return render_template('in.html', mode='admin_menu', user=current_user)

# 管理者メニュー：公式アカウント登録
@app.route('/admin/make_official', methods=['POST'])
def make_official():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    current_user = User.query.get(session['user_id'])
    if not current_user.is_admin:
        return jsonify({'error': 'Forbidden'}), 403
        
    target_username = request.form.get('username')
    target_user = User.query.filter_by(username=target_username).first()
    if target_user:
        target_user.is_official = True
        db.session.commit()
        flash(f'{target_username} を公式アカウントに登録しました。')
    else:
        flash('ユーザーが見つかりません。')
    return redirect(url_for('admin_menu'))
from fastapi.responses import FileResponse

@app.get("/google9645a7e6d72f3e72.html", response_class=FileResponse)
def google_verify():
    # ルートディレクトリにあるhtmlファイルを返します
    return "google9645a7e6d72f3e72.html"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
