import socket
import os
import threading
import hashlib
import shutil
import json

# ===================== 存储配置 =====================
CONFIG_FILE = "pwd_config.json"
MAX_UPLOAD_SIZE = 10 * 1024 * 1024 * 1024    # 单文件最大10GB
WARN_FREE_SPACE = 10 * 1024 * 1024 * 1024    # 剩余<10GB预警
HOST = "0.0.0.0"
PORT = 8888 #仅为示例，请填写与客户端相同的端口
STORAGE_DIR = "server_storage"
BUFFER_SIZE = 16384
# 消息分隔符，解决TCP粘包问题
MSG_SEP = b"|||END_MSG|||"
# =======================================================

# 创建存储目录
if not os.path.exists(STORAGE_DIR):
    os.mkdir(STORAGE_DIR)

# 读写密码配置
def load_server_password():
    """从本地json读取密码，无文件则生成默认密码Cloud@2026"""
    if not os.path.exists(CONFIG_FILE):
        default_pwd = "Cloud@2026"
        save_server_password(default_pwd)
        return default_pwd
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("server_pwd", "Cloud@2026")
    except Exception:
        return "Cloud@2026"

def save_server_password(new_pwd):
    """保存新密码到本地json"""
    data = {"server_pwd": new_pwd}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 统一哈希算法
def calc_pwd_hash(pwd: str):
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()

# 文件名净化防路径穿越
def safe_filename(raw_name: str) -> str:
    name = os.path.basename(raw_name)
    if not name or ".." in name or name.startswith("/") or name.startswith("\\"):
        return ""
    return name

# 字节单位格式化
def format_size(byte_num):
    if byte_num < 1024:
        return f"{byte_num} B"
    elif byte_num < 1024 * 1024:
        return f"{byte_num / 1024:.2f} KB"
    elif byte_num < 1024 * 1024 * 1024:
        return f"{byte_num / (1024*1024):.2f} MB"
    else:
        return f"{byte_num / (1024**3):.2f} GB"

# 获取磁盘空间
def get_disk_space():
    disk = shutil.disk_usage(STORAGE_DIR)
    return disk.total, disk.used, disk.free

# 统计存储目录占用
def get_storage_dir_size():
    total = 0
    for path, dirs, files in os.walk(STORAGE_DIR):
        for f in files:
            fp = os.path.join(path, f)
            total += os.path.getsize(fp)
    return total

# 封装：读取带分隔符的文本消息，解决粘包
def recv_msg(conn) -> str:
    buf = b""
    while MSG_SEP not in buf:
        chunk = conn.recv(BUFFER_SIZE)
        if not chunk:
            return ""
        buf += chunk
    data, _ = buf.split(MSG_SEP, 1)
    return data.decode("utf-8").strip()

# 封装：发送带分隔符消息
def send_msg(conn, text: str):
    conn.send(text.encode("utf-8") + MSG_SEP)

# 单个客户端连接处理
def handle_client(conn, addr, current_pwd_hash):
    print(f"[新连接] {addr} 已接入")
    auth_ok = False

    try:
        # 第一步：密码哈希鉴权（使用分隔符收发）
        client_hash_data = recv_msg(conn)
        if client_hash_data == current_pwd_hash:
            send_msg(conn, "AUTH_SUCCESS")
            auth_ok = True
            print(f"[{addr}] 密码校验通过，允许操作")
        else:
            err_msg = "AUTH_FAILED: 密码错误，连接关闭"
            send_msg(conn, err_msg)
            conn.close()
            print(f"[{addr}] 密码错误，断开连接")
            return

        # 鉴权通过后处理指令
        while True:
            cmd_data = recv_msg(conn)
            if not cmd_data:
                break
            print(f"[{addr}] 收到指令: {cmd_data}")

            # list：文件列表 + 磁盘空间预警
            if cmd_data == "list":
                total_disk, used_disk, free_disk = get_disk_space()
                storage_used = get_storage_dir_size()
                files = os.listdir(STORAGE_DIR)
                file_list = "\n".join(files) if files else "服务器暂无文件"

                space_text = (
                    f"\n===== 磁盘存储状态 =====\n"
                    f"磁盘总容量：{format_size(total_disk)}\n"
                    f"磁盘已使用：{format_size(used_disk)}\n"
                    f"磁盘剩余：{format_size(free_disk)}\n"
                    f"云存储目录占用：{format_size(storage_used)}\n"
                )
                warn_text = ""
                if free_disk < WARN_FREE_SPACE:
                    warn_text = f"\n⚠️ 警告：磁盘剩余空间不足 {format_size(WARN_FREE_SPACE)}，请及时清理文件！\n"
                full_msg = file_list + space_text + warn_text
                send_msg(conn, full_msg)

            # 删除文件
            elif cmd_data.startswith("del "):
                raw_file = cmd_data[4:].strip()
                safe_name = safe_filename(raw_file)
                if not safe_name:
                    msg = "ERROR: 非法文件名，禁止路径穿越"
                    send_msg(conn, msg)
                    continue
                target_path = os.path.join(STORAGE_DIR, safe_name)
                if not os.path.exists(target_path):
                    msg = f"ERROR: 文件 {safe_name} 不存在，删除失败"
                    send_msg(conn, msg)
                    continue
                if os.path.isdir(target_path):
                    msg = f"ERROR: {safe_name} 是文件夹，不支持删除目录"
                    send_msg(conn, msg)
                    continue
                try:
                    os.remove(target_path)
                    msg = f"SUCCESS: 已删除服务器文件 {safe_name}"
                    send_msg(conn, msg)
                    print(f"[{addr}] 删除文件成功：{safe_name}")
                except Exception as e:
                    msg = f"ERROR: 删除失败，异常：{str(e)}"
                    send_msg(conn, msg)

            # 上传文件【修复时序BUG】
            elif cmd_data.startswith("upload "):
                raw_local_path = cmd_data[7:].strip()
                raw_file_name = os.path.basename(raw_local_path)
                safe_name = safe_filename(raw_file_name)
                if not safe_name:
                    send_msg(conn, "ERROR_FILENAME")
                    continue
                # 1. 先发送READY，再等待客户端发送文件大小
                send_msg(conn, "READY_UPLOAD")
                # 读取文件大小
                size_str = recv_msg(conn)
                try:
                    file_size = int(size_str)
                except:
                    send_msg(conn, "ERROR_INVALID_SIZE")
                    continue
                if file_size > MAX_UPLOAD_SIZE:
                    send_msg(conn, "ERROR_OVERSIZE")
                    continue
                _, _, free_disk = get_disk_space()
                if file_size > free_disk:
                    send_msg(conn, "ERROR_DISK_FULL")
                    continue

                save_path = os.path.join(STORAGE_DIR, safe_name)
                received_size = 0
                with open(save_path, "wb") as f:
                    while received_size < file_size:
                        chunk = conn.recv(BUFFER_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        received_size += len(chunk)
                finish_msg = f"上传完成：{safe_name}"
                send_msg(conn, finish_msg)

            # 下载文件
            elif cmd_data.startswith("download "):
                raw_file = cmd_data[9:].strip()
                safe_name = safe_filename(raw_file)
                if not safe_name:
                    send_msg(conn, "FILE_NOT_EXIST")
                    continue
                file_path = os.path.join(STORAGE_DIR, safe_name)
                if not os.path.exists(file_path):
                    send_msg(conn, "FILE_NOT_EXIST")
                    continue
                file_size = os.path.getsize(file_path)
                send_msg(conn, str(file_size))
                # 等待客户端就绪信号
                client_ack = recv_msg(conn)
                if client_ack != "START_DOWNLOAD":
                    continue
                with open(file_path, "rb") as f:
                    while chunk := f.read(BUFFER_SIZE):
                        conn.send(chunk)
                # 文件数据流发送完毕后，发送结束标记文本消息
                send_msg(conn, "DOWNLOAD_FINISH")

            # 无效指令
            else:
                err_msg = "ERROR: 无效指令，支持 list / upload [路径] / download [文件名] / del [文件名]"
                send_msg(conn, err_msg)

    except Exception as e:
        print(f"[{addr}] 连接异常: {e}")
    finally:
        conn.close()
        print(f"[{addr}] 连接已断开")

def start_server():
    # 加载当前运行密码
    current_pwd = load_server_password()
    current_pwd_hash = calc_pwd_hash(current_pwd)

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(128)
    print("="*50)
    print(f"云存储服务端启动成功，监听 {HOST}:{PORT}")
    print(f"当前访问密码：{current_pwd}")
    print(f"磁盘剩余预警阈值：{format_size(WARN_FREE_SPACE)}")
    print("输入 setpwd 修改访问密码，输入 start 启动服务监听")
    print("="*50)

    # 服务端控制台交互：修改密码
    while True:
        opt = input("\nServer Console ==> ").strip()
        if opt == "start":
            print("开始接受客户端连接...")
            break
        elif opt == "setpwd":
            new_pwd = input("请输入新的云存储访问密码：").strip()
            if len(new_pwd) < 4:
                print("密码长度不能小于4位，修改失败！")
                continue
            save_server_password(new_pwd)
            print(f"密码已保存至 {CONFIG_FILE}")
            print("⚠️ 重要：修改密码后必须重启服务端程序才能生效！")

        else:
            print("可用命令：setpwd(修改密码) / start(启动监听)")

    # 循环接收客户端
    while True:
        conn, addr = server_sock.accept()
        t = threading.Thread(target=handle_client, args=(conn, addr, current_pwd_hash))
        t.daemon = True
        t.start()

if __name__ == "__main__":
    start_server()