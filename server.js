const express = require('express');
const http = require('http');
const socketIo = require('socket.io');
const { io: Client } = require('socket.io-client');

const app = express();
const server = http.createServer(app);
const io = socketIo(server);

let pythonSocket = null;

function connectPythonSocket() {
    const socket = Client('http://127.0.0.1:5000', {
        reconnection: true,
        reconnectionDelay: 5000,
    });

    socket.on('connect', () => {
        console.log('成功連接到 Python Socket.IO 伺服器');
        pythonSocket = socket;
    });

    socket.on('frame', (data) => {
        console.log('收到 Python 端影像數據，大小:', data.frame.length, '字元');
        // 只傳送 base64 字符串
        io.emit('frame', data.frame);
    });

    socket.on('object_counts', (data) => {
        console.log('收到 Python 端物件計數數據:', data);
        io.emit('object_counts', data);
    });

    socket.on('connect_error', (error) => {
        console.error('Socket.IO 連線錯誤:', error.message);
    });

    socket.on('disconnect', () => {
        console.log('Socket.IO 連線關閉，嘗試重新連線...');
        pythonSocket = null;
    });
}

io.on('connection', (socket) => {
    console.log('前端已連線，Socket ID:', socket.id);

    socket.on('control', (data) => {
        console.log('收到前端控制指令:', data);
        if (pythonSocket && pythonSocket.connected) {
            pythonSocket.emit('control', data);
            console.log('已將控制指令發送到 Python 後端');
        } else {
            console.log('Python Socket.IO 未連接，無法發送控制指令');
        }
    });

    socket.on('disconnect', () => {
        console.log('前端已斷線，Socket ID:', socket.id);
    });
});

connectPythonSocket();

app.use(express.static('public'));

server.listen(3000, () => {
    console.log('伺服器運行於 http://localhost:3000');
});