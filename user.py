import socket
import os
import time
import hashlib
from colorama import Fore

def cloud_storage_user():
    # 安全配置区
    SERVER_IP = "39.163.172.7"  # 内网填局域网IP，公网填服务器公网IP
    SERVER_PORT = 8888
    DOWNLOAD_DIR = "client_download"
    BUFFER_SIZE = 16384
    MSG_SEP = b"|||END_MSG|||"  # 和服务端保持一致分隔符

    # 统一哈希算法
    def calc_pwd_hash(pwd: str):
        return hashlib.sha256(pwd.encode("utf-8")).hexdigest()

    # 封装：接收带分隔符完整文本消息
    def recv_msg(sock) -> str:
        buf = b""
        while MSG_SEP not in buf:
            chunk = sock.recv(BUFFER_SIZE)
            if not chunk:
                return ""
            buf += chunk
        data, _ = buf.split(MSG_SEP, 1)
        return data.decode("utf-8").strip()

    # 封装：发送带分隔符文本消息
    def send_msg(sock, text: str):
        sock.send(text.encode("utf-8") + MSG_SEP)

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
        # 原生TCP Socket，设置30秒超时防止卡死
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect((SERVER_IP, SERVER_PORT))
        colorPrint("green", f"成功连接云存储服务器 {SERVER_IP}:{SERVER_PORT}")
        # 密码哈希鉴权流程
        colorPrint("yellow", "请输入云存储访问密码：")
        input_pwd = input(Fore.YELLOW + "pwd==>").strip()
        client_hash = calc_pwd_hash(input_pwd)
        send_msg(sock, client_hash)
        auth_result = recv_msg(sock)
        if auth_result != "AUTH_SUCCESS":
            colorPrint("red", f"访问拒绝：{auth_result}，连接断开")
            sock.close()
            return
        colorPrint("green", "密码校验通过，云存储终端就绪")
        colorPrint("blue", "输入 help 查看云存储可用指令，输入 exit 退出云存储终端")
    except Exception as e:
        colorPrint("red", f"连接服务器失败：{e}，请先启动服务端server.py，检查IP/端口/防火墙")
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
            # 发送指令到服务端（带分隔符）
            send_msg(sock, user_cmd)
            # 1. list 查看文件列表 + 磁盘空间预警
            if user_cmd == "list":
                resp = recv_msg(sock)
                colorPrint("cyan", "===== 服务器文件列表 & 存储状态 =====")
                print(resp)
            # 2. del 远程删除服务器文件
            elif user_cmd.startswith("del "):
                result = recv_msg(sock)
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
                # 接收服务端就绪信号
                resp_text = recv_msg(sock)
                if resp_text != "READY_UPLOAD":
                    colorPrint("red", f"服务器拒绝接收文件：{resp_text}")
                    continue
                file_size = os.path.getsize(local_path)
                send_msg(sock, str(file_size))
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
                msg = recv_msg(sock)
                colorPrint("green", msg)
            # 4. download 下载文件
            elif user_cmd.startswith("download "):
                file_name = user_cmd[9:].strip()
                size_str = recv_msg(sock)
                if size_str == "FILE_NOT_EXIST":
                    colorPrint("red", f"服务器不存在文件：{file_name}")
                    continue
                file_size = int(size_str)
                send_msg(sock, "START_DOWNLOAD")
                save_path = os.path.join(DOWNLOAD_DIR, file_name)
                received = 0
                start_time = time.time()
                with open(save_path, "wb") as f:
                    while received < file_size:
                        chunk = sock.recv(BUFFER_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)
                        cost = time.time() - start_time
                        avg_spd = received / cost if cost > 0 else 0
                        print_progress(received, file_size, avg_spd)
                print()
                # 读取下载完成文本提示
                finish_tip = recv_msg(sock)
                colorPrint("green", f"下载完成，保存路径：{save_path} | 服务端反馈：{finish_tip}")
            # 未知指令
            else:
                err_msg = recv_msg(sock)
                colorPrint("red", err_msg)
        except socket.timeout:
            colorPrint("red", "网络超时，连接断开")
            if sock:
                sock.close()
            break
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