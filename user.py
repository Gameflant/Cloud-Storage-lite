import socket
import os
import time
import hashlib
from colorama import Fore

def cloud_storage_user():
    # 安全配置区
    SERVER_IP = "127.0.0.1"  #替换成自己的服务器ip地址
    SERVER_PORT = 8888  #这里仅为示例，请填写与服务端相同的端口
    DOWNLOAD_DIR = "client_download"
    BUFFER_SIZE = 16384

    # 统一哈希算法
    def calc_pwd_hash(pwd: str):
        return hashlib.sha256(pwd.encode("utf-8")).hexdigest()

    # 单位格式化工具
    def format_size(byte_num):
        if byte_num < 1024:
            return f"{byte_num} B"
        elif byte_num < 1024 * 1024:
            return f"{byte_num / 1024:.2f} KB"
        elif byte_num < 1024 * 1024 * 1024:
            return f"{byte_num / (1024*1024):.2f} MB"
        else:
            return f"{byte_num / (1024**3):.2f} GB"

    # 打印进度条
    def print_progress(now, total, avg_speed):
        bar_len = 30
        percent = now / total if total != 0 else 0
        fill = int(bar_len * percent)
        bar = "█" * fill + "░" * (bar_len - fill)
        now_str = format_size(now)
        total_str = format_size(total)
        speed_str = format_size(avg_speed) + "/s"
        print(f"\r{Fore.GREEN}[{bar}] {percent*100:.1f}% | {now_str}/{total_str} | 平均速度:{speed_str}", end="", flush=True)

    # 颜色打印工具
    def colorPrint(color, text):
        if color == 'red':
            print(Fore.RED + str(text))
        elif color == 'green':
            print(Fore.GREEN + str(text))
        elif color == 'yellow':
            print(Fore.YELLOW + str(text))
        elif color == 'blue':
            print(Fore.BLUE + str(text))
        elif color == 'cyan':
            print(Fore.CYAN + str(text))
        else:
            print(Fore.RESET + str(text))

    # 创建本地下载文件夹
    if not os.path.exists(DOWNLOAD_DIR):
        os.mkdir(DOWNLOAD_DIR)
        colorPrint("green", f"自动创建下载目录：{DOWNLOAD_DIR}")
    sock = None
    try:
        # 原生TCP Socket，无超时限制
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((SERVER_IP, SERVER_PORT))
        colorPrint("green", f"成功连接云存储服务器 {SERVER_IP}:{SERVER_PORT}")
        # 密码哈希鉴权流程
        colorPrint("yellow", "请输入云存储访问密码：")
        input_pwd = input(Fore.YELLOW + "pwd==>").strip()
        client_hash = calc_pwd_hash(input_pwd)
        sock.send(client_hash.encode("utf-8"))
        auth_result = sock.recv(BUFFER_SIZE).decode("utf-8")
        if auth_result != "AUTH_SUCCESS":
            colorPrint("red", f"访问拒绝：{auth_result}，连接断开")
            sock.close()
            return
        colorPrint("green", "密码校验通过，云存储终端就绪")
        colorPrint("blue", "输入 help 查看云存储可用指令，输入 exit 退出云存储终端")
    except Exception as e:
        colorPrint("red", f"连接服务器失败：{e}，请先启动服务端server.py")
        return
    # 云存储交互循环
    while True:
        try:
            user_cmd = input(Fore.BLUE + 'cloud-storage==>').strip()
            if not user_cmd:
                continue
            # 退出云存储终端
            if user_cmd == 'exit':
                colorPrint("blue", "断开云存储连接，程序退出")
                sock.close()
                break
            # 帮助命令
            if user_cmd == 'help':
                colorPrint('blue', """[cloud-storage 指令说明]
list               # 查看服务器全部文件 + 磁盘存储空间状态
upload [本地文件路径] # 上传本地文件到服务器（带进度+平均测速）
download [文件名]    # 下载服务器文件到本地client_download文件夹
del [文件名]         # 远程删除服务器上指定文件
help               # 查看指令帮助
exit               # 退出云存储终端""")
                continue
            # 发送指令到服务端
            sock.send(user_cmd.encode("utf-8"))
            # 1. list 查看文件列表 + 磁盘空间预警
            if user_cmd == "list":
                resp = sock.recv(BUFFER_SIZE).decode("utf-8")
                colorPrint("cyan", "===== 服务器文件列表 & 存储状态 =====")
                print(resp)
            # 2. del 远程删除服务器文件
            elif user_cmd.startswith("del "):
                result = sock.recv(BUFFER_SIZE).decode("utf-8")
                if result.startswith("SUCCESS"):
                    colorPrint("green", result)
                else:
                    colorPrint("red", result)
            # 3. upload 上传文件
            elif user_cmd.startswith("upload "):
                local_path = user_cmd[7:].strip()
                if not os.path.isfile(local_path):
                    colorPrint("red", f"本地文件不存在：{local_path}")
                    continue
                resp = sock.recv(BUFFER_SIZE)
                if resp != b"READY_UPLOAD":
                    colorPrint("red", "服务器拒绝接收文件")
                    continue
                file_size = os.path.getsize(local_path)
                sock.send(str(file_size).encode("utf-8"))
                uploaded = 0
                start_time = time.time()
                with open(local_path, "rb") as f:
                    while chunk := f.read(BUFFER_SIZE):
                        sock.send(chunk)
                        uploaded += len(chunk)
                        cost = time.time() - start_time
                        avg_spd = uploaded / cost if cost > 0 else 0
                        print_progress(uploaded, file_size, avg_spd)
                print()
                msg = sock.recv(BUFFER_SIZE).decode("utf-8")
                colorPrint("green", msg)
            # 4. download 下载文件
            elif user_cmd.startswith("download "):
                file_name = user_cmd[9:].strip()
                size_data = sock.recv(BUFFER_SIZE)
                if size_data == b"FILE_NOT_EXIST":
                    colorPrint("red", f"服务器不存在文件：{file_name}")
                    continue
                file_size = int(size_data.decode("utf-8"))
                sock.send(b"START_DOWNLOAD")
                save_path = os.path.join(DOWNLOAD_DIR, file_name)
                received = 0
                start_time = time.time()
                with open(save_path, "wb") as f:
                    while received < file_size:
                        chunk = sock.recv(BUFFER_SIZE)
                        if chunk == b"DOWNLOAD_FINISH":
                            break
                        f.write(chunk)
                        received += len(chunk)
                        cost = time.time() - start_time
                        avg_spd = received / cost if cost > 0 else 0
                        print_progress(received, file_size, avg_spd)
                print()
                colorPrint("green", f"下载完成，保存路径：{save_path}")
            # 未知指令
            else:
                err_msg = sock.recv(BUFFER_SIZE).decode("utf-8")
                colorPrint("red", err_msg)
        except ConnectionResetError:
            colorPrint("red", "服务器连接已断开，程序退出")
            if sock:
                sock.close()
            break
        except Exception as e:
            colorPrint("red", f"操作异常：{e}")
    return

if __name__ == "__main__":
    print(Fore.CYAN + "===== 独立云存储客户端 CDSE =====")
    cloud_storage_user()
