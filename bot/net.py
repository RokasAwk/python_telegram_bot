import socket

# 主機（例如會睡眠的 Mac）從睡眠中醒來後，連線池裡的舊 TCP 連線可能早就死了，但本地端看起來還是
# 「已建立」。開啟 TCP keepalive 讓作業系統主動探測、快速判定連線已死掉，
# 避免要等到預設的 TCP 重傳逾時（可能長達十幾分鐘）才發現連線壞了。
KEEPALIVE_SOCKET_OPTIONS: list[tuple] = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
if hasattr(socket, "TCP_KEEPIDLE"):
    KEEPALIVE_SOCKET_OPTIONS.append((socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30))
if hasattr(socket, "TCP_KEEPINTVL"):
    KEEPALIVE_SOCKET_OPTIONS.append((socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10))
if hasattr(socket, "TCP_KEEPCNT"):
    KEEPALIVE_SOCKET_OPTIONS.append((socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3))
