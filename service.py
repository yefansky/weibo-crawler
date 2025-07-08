from weibo import Weibo, handle_config_renaming
from weibo import get_config as get_config_from_file
import const
import logging
import logging.config
import os
from flask import Flask, jsonify, request
import sqlite3
import json
from concurrent.futures import ThreadPoolExecutor
import threading
import uuid
import time
from datetime import datetime

# 1896820725 天津股侠 2024-12-09T16:47:04

DATABASE_PATH = './weibo/weibodata.db'
print(DATABASE_PATH)

# 如果日志文件夹不存在，则创建
if not os.path.isdir("log/"):
    os.makedirs("log/")
logging_path = os.path.split(os.path.realpath(__file__))[0] + os.sep + "logging.conf"
logging.config.fileConfig(logging_path)
logger = logging.getLogger("api")

config = {
    "user_id_list": [],#"user_id_list.txt",
    "only_crawl_original": 0,
    "since_date": 1,
    "start_page": 1,
    "page_weibo_count": 10,
    "write_mode": [
        "sqlite"
    ],
    "original_pic_download": 1,
    "retweet_pic_download": 0,
    "original_video_download": 1,
    "retweet_video_download": 0,
    "original_live_photo_download": 1,
    "retweet_live_photo_download": 0,
    "download_comment": 1,
    "comment_max_download_count": 100,
    "download_repost": 1,
    "repost_max_download_count": 100,
    "user_id_as_folder_name": 0,
    "remove_html_tag": 1,
    "cookie": "your cookie",
    "mysql_config": {
        "host": "localhost",
        "port": 3306,
        "user": "root",
        "password": "123456",
        "charset": "utf8mb4"
    },
    "store_binary_in_sqlite": 0,
    "mongodb_URI": "mongodb://[username:password@]host[:port][/[defaultauthdb][?options]]",
    "post_config": {
        "api_url": "https://api.example.com",
        "api_token": ""
    }
}

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 确保JSON响应中的中文不会被转义
app.config['JSONIFY_MIMETYPE'] = 'application/json;charset=utf-8'

# 添加线程池和任务状态跟踪
executor = ThreadPoolExecutor(max_workers=1)  # 限制只有1个worker避免并发爬取
tasks = {}  # 存储任务状态

# 在executor定义后添加任务锁相关变量
current_task_id = None
task_lock = threading.Lock()

def get_running_task():
    """获取当前运行的任务信息"""
    if current_task_id and current_task_id in tasks:
        task = tasks[current_task_id]
        if task['state'] in ['PENDING', 'PROGRESS']:
            return current_task_id, task
    return None, None

def get_config(user_id_list=None):
    """获取配置，允许动态设置user_id_list"""
    current_config = config.copy()
    if user_id_list:
        current_config['user_id_list'] = user_id_list
    handle_config_renaming(current_config, oldName="filter", newName="only_crawl_original")
    handle_config_renaming(current_config, oldName="result_dir_name", newName="user_id_as_folder_name")
    return current_config

def run_refresh_task(task_id, config):
    global current_task_id
    try:
        tasks[task_id]['state'] = 'PROGRESS'
        tasks[task_id]['progress'] = 0
        
        wb = Weibo(config)
        tasks[task_id]['progress'] = 50
        
        wb.start()  # 爬取微博信息
        tasks[task_id]['progress'] = 100
        tasks[task_id]['state'] = 'SUCCESS'
        tasks[task_id]['result'] = {"message": "微博列表已刷新"}
        
    except Exception as e:
        tasks[task_id]['state'] = 'FAILED'
        tasks[task_id]['error'] = str(e)
        logger.exception(e)
    finally:
        with task_lock:
            if current_task_id == task_id:
                current_task_id = None

@app.route('/get_status')
def get_status():
    return "ok", 200

@app.route('/refresh', methods=['POST'])
def refresh():
    global current_task_id
    
    # 获取请求参数
    config_data = new_func()
    user_id_list = config_data.get('user_id_list') if config_data else None
    
    # 验证参数
    if not user_id_list or not isinstance(user_id_list, list):
        return jsonify({
            'error': 'Invalid user_id_list parameter'
        }), 400
    
    # 检查是否有正在运行的任务
    with task_lock:
        running_task_id, running_task = get_running_task()
        if running_task:
            return jsonify({
                'task_id': running_task_id,
                'status': 'Task already running',
                'state': running_task['state'],
                'progress': running_task['progress']
            }), 409  # 409 Conflict
        
        # 创建新任务
        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            'state': 'PENDING',
            'progress': 0,
            'created_at': datetime.now().isoformat(),
            'user_id_list': user_id_list
        }
        current_task_id = task_id
        
    executor.submit(run_refresh_task, task_id, config_data)
    return jsonify({
        'task_id': task_id,
        'status': 'Task started',
        'state': 'PENDING',
        'progress': 0,
        'user_id_list': user_id_list
    }), 202

def new_func():
    data = request.get_json()
    return data

@app.route('/task/<task_id>', methods=['GET'])
def get_task_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
        
    response = {
        'state': task['state'],
        'progress': task['progress']
    }
    
    if task['state'] == 'SUCCESS':
        response['result'] = task.get('result')
    elif task['state'] == 'FAILED':
        response['error'] = task.get('error')
        
    return jsonify(response)

def get_sqlite_connection():
    wb = Weibo(config)
    return wb.get_sqlite_connection()

@app.route('/weibos', methods=['GET'])
def get_weibos():
    try:
        conn = get_sqlite_connection()
        cursor = conn.cursor()
        
        # 修改后的SQL：关联weibo表和user表获取avatar_url
        query = """
        SELECT 
            w.*, 
            u.avatar_url AS user_avatar_url 
        FROM weibo w
        LEFT JOIN user u ON w.user_id = u.id
        ORDER BY w.created_at DESC
        """
        cursor.execute(query)
        
        columns = [column[0] for column in cursor.description]
        weibos = []
        for row in cursor.fetchall():
            weibo = dict(zip(columns, row))
            weibos.append(weibo)
            
        conn.close()
        return jsonify(weibos), 200
        
    except Exception as e:
        logger.exception(e)
        return {"error": str(e)}, 500
    
@app.route('/weibo_comments/<weibo_id>', methods=['GET'])
def get_weibo_comments(weibo_id):
    """获取指定微博的评论数据"""
    try:
        conn = get_sqlite_connection()
        cursor = conn.cursor()
        
        # 查询指定微博的评论，按时间倒序排列
        query = """
        SELECT 
            id, user_screen_name, user_avatar_url, text, created_at, like_count
        FROM comments 
        WHERE weibo_id = ?
        ORDER BY created_at DESC
        """
        cursor.execute(query, (weibo_id,))
        
        columns = [column[0] for column in cursor.description]
        comments = []
        for row in cursor.fetchall():
            comment = dict(zip(columns, row))
            comments.append(comment)
            
        conn.close()
        return jsonify({"comments": comments}), 200
        
    except Exception as e:
        logger.exception(e)
        return {"error": str(e)}, 500
    
def init_db():
    """初始化数据库"""
    conn = get_sqlite_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS config
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  config_json TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def save_config(config):
    """保存配置到数据库"""
    conn = get_sqlite_connection()
    c = conn.cursor()
    c.execute("INSERT INTO config (config_json) VALUES (?)", (json.dumps(config),))
    conn.commit()
    conn.close()

def load_config():
    """从数据库加载最新配置"""
    conn = get_sqlite_connection()
    c = conn.cursor()
    c.execute("SELECT config_json FROM config ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None

@app.route('/save_config', methods=['POST'])
def handle_save_config():
    init_db()
    config = request.json
    save_config(config)
    return jsonify({"status": "success"}), 200

@app.route('/get_config', methods=['GET'])
def handle_get_config():
    config = load_config()
    if config:
        return jsonify(config), 200
    else:
        return jsonify({"error": "No config found"}), 404

@app.route('/weibos/<weibo_id>', methods=['GET'])
def get_weibo_detail(weibo_id):
    try:
        conn = get_sqlite_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM weibo WHERE id=?", (weibo_id,))
        columns = [column[0] for column in cursor.description]
        row = cursor.fetchone()
        conn.close()
        
        if row:
            weibo = dict(zip(columns, row))
            return jsonify(weibo), 200
        else:
            return {"error": "Weibo not found"}, 404
    except Exception as e:
        logger.exception(e)
        return jsonify({"id": weibo_id, "error": str(e), "comments": []}), 500

def schedule_refresh():
    """定时刷新任务"""
    while True:
        try:
            # 检查是否有运行中的任务
            running_task_id, running_task = get_running_task()
            if not running_task:
                task_id = str(uuid.uuid4())
                tasks[task_id] = {
                    'state': 'PENDING',
                    'progress': 0,
                    'created_at': datetime.now().isoformat(),
                    'user_id_list': config['user_id_list']  # 使用默认配置
                }
                with task_lock:
                    global current_task_id
                    current_task_id = task_id
                executor.submit(run_refresh_task, task_id, config)
                logger.info(f"Scheduled task {task_id} started")
            
            time.sleep(600)  # 10分钟间隔
        except Exception as e:
            logger.exception("Schedule task error")
            time.sleep(60)  # 发生错误时等待1分钟后重试

@app.route('/clear_data', methods=['GET'])
def clear_data():
    """清空数据库中的所有微博数据"""
    try:
        # 检查是否有正在运行的任务
        with task_lock:
            running_task_id, running_task = get_running_task()
            if running_task:
                return jsonify({
                    'error': 'Cannot clear data while a task is running',
                    'task_id': running_task_id,
                    'state': running_task['state']
                }), 409  # 409 Conflict
        
        # 获取数据库连接
        conn = get_sqlite_connection()
        cursor = conn.cursor()
        
        # 清空所有相关表
        cursor.execute("DELETE FROM weibo")
        cursor.execute("DELETE FROM comments")
        cursor.execute("DELETE FROM reposts")
        cursor.execute("DELETE FROM user")
        cursor.execute("DELETE FROM bins")
        
        # 重置自增ID
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('weibo', 'comments', 'reposts', 'user', 'bins')")
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'message': 'All data has been cleared',
            'tables_cleared': ['weibo', 'comments', 'reposts', 'user', 'bins']
        }), 200
        
    except Exception as e:
        logger.exception(e)
        return jsonify({
            'error': str(e),
            'message': 'Failed to clear data'
        }), 500

if __name__ == "__main__":
    # 启动定时任务线程
    scheduler_thread = threading.Thread(target=schedule_refresh, daemon=True)
    scheduler_thread.start()
    
    logger.info("服务启动")
    # 启动Flask应用
    app.run(debug=True, use_reloader=False)  # 关闭reloader避免启动两次