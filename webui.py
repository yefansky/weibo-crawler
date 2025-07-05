import streamlit as st
import requests
import time
import subprocess
import psutil
import os
import signal
import json
import sys  # 添加 sys 模块获取 Python 路径

# Flask 服务配置
FLASK_PORT = 5000
FLASK_URL = f"http://localhost:{FLASK_PORT}"
SERVICE_PY_PATH = os.path.abspath("./service.py")  # 使用绝对路径

def get_current_python():
    """获取当前虚拟环境的 Python 解释器路径"""
    return sys.executable

def check_service_running():
    """检查 Flask 服务是否正在运行"""
    try:
        response = requests.get(f"{FLASK_URL}/get_status", timeout=2)
        return response.status_code == 200
    except requests.ConnectionError:
        return False

def start_flask_service():
    """使用当前环境的 Python 解释器启动 Flask 服务"""
    if not check_service_running():
        # 获取当前 Python 解释器路径
        python_executable = get_current_python()
        
        # 启动服务（使用当前环境的 Python）
        process = subprocess.Popen(
            [python_executable, SERVICE_PY_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy(),  # 继承当前环境变量
            start_new_session=True  # 创建新会话，确保独立运行
        )
        st.session_state.flask_process = process
        time.sleep(3)  # 等待服务启动

def stop_flask_service():
    """停止 Flask 服务"""
    # 首先尝试通过进程对象停止
    if 'flask_process' in st.session_state:
        try:
            process = st.session_state.flask_process
            if process.poll() is None:  # 检查进程是否仍在运行
                process.terminate()
                process.wait(timeout=3)
        except Exception as e:
            st.error(f"停止服务时出错: {str(e)}")
    
    # 回退方法：通过端口查找并终止进程
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.status == 'LISTEN' and conn.laddr.port == FLASK_PORT:
                proc = psutil.Process(conn.pid)
                proc.terminate()
    except Exception as e:
        st.error(f"回退停止方法出错: {str(e)}")
    
    # 确保进程已停止
    time.sleep(1)
    if 'flask_process' in st.session_state:
        del st.session_state.flask_process

def trigger_refresh(config_data):
    """触发微博刷新任务"""
    try:
        # 确保使用 SQLite 作为存储模式
        config_data['write_mode'] = ['sqlite']
        
        response = requests.post(
            f"{FLASK_URL}/refresh",
            json = config_data
        )
        return response.json() if response.status_code == 202 else None
    except requests.ConnectionError:
        return None

def get_task_status(task_id):
    """获取任务状态"""
    try:
        response = requests.get(f"{FLASK_URL}/task/{task_id}")
        return response.json() if response.status_code == 200 else None
    except requests.ConnectionError:
        return None

def get_weibos():
    """获取微博列表"""
    try:
        response = requests.get(f"{FLASK_URL}/weibos")
        return response.json() if response.status_code == 200 else []
    except requests.ConnectionError:
        return []

def get_weibo_detail(weibo_id):
    """获取微博详情"""
    try:
        response = requests.get(f"{FLASK_URL}/weibos/{weibo_id}")
        return response.json() if response.status_code == 200 else None
    except requests.ConnectionError:
        return None

# Streamlit 应用界面
st.set_page_config(
    page_title="微博数据监控平台",
    page_icon="📱",
    layout="wide"
)

# 初始化 session state
if 'task_id' not in st.session_state:
    st.session_state.task_id = None
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = None
if 'config' not in st.session_state:
    st.session_state.config = {
        "user_id_list": ["6067225218", "1445403190"],
        "only_crawl_original": 1,
        "since_date": 1,
        "start_page": 1,
        "write_mode": ["sqlite"],
        "download_comment": 1,
        "comment_max_download_count": 1000,
        "download_repost": 0,
        "repost_max_download_count": 100,
        "remove_html_tag": 1
    }
if 'flask_process' not in st.session_state:
    st.session_state.flask_process = None

# 标题区域
st.title("📱 微博数据监控平台")
st.markdown("监控指定微博账号的最新动态，实时获取数据更新")

# 服务状态管理
st.header("服务管理")
service_col1, service_col2, service_col3 = st.columns([1, 1, 2])

with service_col1:
    service_status = "🟢 运行中" if check_service_running() else "🔴 已停止"
    st.metric("服务状态", service_status)

with service_col2:
    if check_service_running():
        if st.button("停止服务", help="停止后台微博数据服务"):
            stop_flask_service()
            time.sleep(1)
            st.rerun()
    else:
        if st.button("启动服务", help="启动后台微博数据服务", type="primary"):
            start_flask_service()
            time.sleep(1)
            st.rerun()

with service_col3:
    if st.button("重启服务", help="重启后台微博数据服务"):
        stop_flask_service()
        time.sleep(1)
        start_flask_service()
        time.sleep(1)
        st.rerun()

# 显示当前 Python 环境信息
st.caption(f"当前 Python 环境: `{get_current_python()}`")
st.caption(f"服务文件路径: `{SERVICE_PY_PATH}`")

# 配置设置区域
st.header("配置设置")
with st.expander("微博爬取配置"):
    # 用户ID列表配置
    user_ids = st.text_area(
        "微博用户ID列表（每行一个ID）", 
        value="\n".join(st.session_state.config["user_id_list"]),
        height=150,
        key="user_id_list"
    )
    st.session_state.config["user_id_list"] = [uid.strip() for uid in user_ids.split("\n") if uid.strip()]
    
    # 其他配置选项
    col1, col2 = st.columns(2)
    
    with col1:
        st.session_state.config["only_crawl_original"] = int(st.checkbox(
            "仅爬取原创微博", 
            value=bool(st.session_state.config["only_crawl_original"]),
            key="only_original"
        ))
        
        st.session_state.config["download_comment"] = int(st.checkbox(
            "下载评论", 
            value=bool(st.session_state.config["download_comment"]),
            key="download_comment"
        ))
        
        st.session_state.config["download_repost"] = int(st.checkbox(
            "下载转发", 
            value=bool(st.session_state.config["download_repost"]),
            key="download_repost"
        ))
    
    with col2:
        st.session_state.config["comment_max_download_count"] = st.number_input(
            "最大评论下载数量", 
            min_value=1, 
            max_value=5000, 
            value=st.session_state.config["comment_max_download_count"],
            key="comment_max"
        )
        
        st.session_state.config["repost_max_download_count"] = st.number_input(
            "最大转发下载数量", 
            min_value=1, 
            max_value=5000, 
            value=st.session_state.config["repost_max_download_count"],
            key="repost_max"
        )
        
        st.session_state.config["since_date"] = st.number_input(
            "爬取天数（最近N天）", 
            min_value=1, 
            max_value=30, 
            value=st.session_state.config["since_date"],
            key="since_date"
        )
    
    # 存储模式固定为 SQLite
    st.info("存储模式固定为 SQLite")
    st.session_state.config["write_mode"] = ["sqlite"]
    
    # 显示当前配置
    if st.button("查看当前配置", key="view_config"):
        st.json(st.session_state.config)

# 微博刷新功能
st.header("数据刷新")
if check_service_running():
    if st.button("立即刷新微博", type="primary", key="refresh_btn"):
        # 确保配置值为整数（Weibo库要求）
        int_config = st.session_state.config.copy()
        
        result = trigger_refresh(int_config)
        if result and 'task_id' in result:
            st.session_state.task_id = result['task_id']
            st.session_state.last_refresh = time.time()
            st.success("刷新任务已启动!")
        else:
            st.error("刷新任务启动失败，请检查服务状态")
    
    # 显示任务状态
    if st.session_state.task_id:
        task_status = get_task_status(st.session_state.task_id)
        if task_status:
            state = task_status['state']
            progress = task_status['progress']
            
            if state == 'SUCCESS':
                st.success(f"✅ 任务完成: {task_status.get('result', {}).get('message', '')}")
                st.session_state.task_id = None
            elif state == 'FAILED':
                st.error(f"❌ 任务失败: {task_status.get('error', '未知错误')}")
                st.session_state.task_id = None
            elif state == 'PROGRESS':
                st.progress(progress / 100, text=f"🔄 刷新中... {progress}%")
            elif state == 'PENDING':
                st.info("⏳ 任务等待中...")
                
            # 自动刷新状态
            st.rerun()
    
    if st.session_state.last_refresh:
        elapsed = int(time.time() - st.session_state.last_refresh)
        st.caption(f"上次刷新时间: {time.ctime(st.session_state.last_refresh)} ({elapsed}秒前)")
else:
    st.warning("服务未运行，请先启动服务")

# 微博数据展示
st.header("微博数据")
if check_service_running():
    weibos = get_weibos()
    
    if weibos:
        # 搜索和筛选
        search_col, filter_col = st.columns([3, 1])
        with search_col:
            search_term = st.text_input("搜索微博内容", "", key="search_term")
        with filter_col:
            show_original = st.checkbox("仅显示原创", True, key="show_original")
        
        # 显示微博列表
        for weibo in weibos:
            # 应用筛选
            if show_original and weibo.get('retweet_id'):
                continue
            if search_term and search_term.lower() not in weibo.get('text', '').lower():
                continue
            
            with st.expander(f"{weibo.get('user_name', '未知用户')} - {weibo.get('created_at', '未知时间')}"):
                # 创建两列布局
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # 微博内容
                    st.markdown(f"**{weibo.get('text', '')}**")
                    
                    # 元数据
                    meta_cols = st.columns(4)
                    meta_cols[0].metric("点赞", weibo.get('attitudes_count', 0))
                    meta_cols[1].metric("评论", weibo.get('comments_count', 0))
                    meta_cols[2].metric("转发", weibo.get('reposts_count', 0))
                    
                    if weibo.get('retweet_id'):
                        meta_cols[3].metric("类型", "转发微博")
                    else:
                        meta_cols[3].metric("类型", "原创微博")
                
                with col2:
                    # 用户信息
                    st.image(weibo.get('user_profile_image_url', 'https://via.placeholder.com/100'), 
                             width=100, caption=weibo.get('user_name', '未知用户'))
                    
                    if st.button("查看详情", key=f"detail_{weibo['id']}"):
                        detail = get_weibo_detail(weibo['id'])
                        if detail:
                            st.session_state[f"detail_{weibo['id']}"] = detail
                
                # 显示详情（如果已加载）
                if f"detail_{weibo['id']}" in st.session_state:
                    detail = st.session_state[f"detail_{weibo['id']}"]
                    st.subheader("微博详情")
                    
                    # 显示评论数据
                    if 'comments' in detail and detail['comments']:
                        st.markdown(f"**评论 ({len(detail['comments'])}条):**")
                        for comment in detail['comments']:
                            st.markdown(f"- **{comment.get('user_name', '匿名')}**: {comment.get('text', '')}")
                    else:
                        st.info("没有评论数据")
                    
                    if st.button("关闭详情", key=f"close_{weibo['id']}"):
                        del st.session_state[f"detail_{weibo['id']}"]
                        st.rerun()
        
        st.info(f"显示 {len(weibos)} 条微博数据")
    else:
        st.warning("没有获取到微博数据，请尝试刷新")
else:
    st.warning("服务未运行，无法获取数据")

# 页脚信息
st.divider()
st.caption("微博数据监控平台 v3.0 | 数据每10分钟自动刷新 | 存储模式: SQLite")
st.caption(f"运行环境: Python {sys.version}")