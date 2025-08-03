import { Injectable, OnDestroy } from '@angular/core';
import { Subject } from 'rxjs';

import { ImageEditMessage } from '../models/image-edit-msg';
import { SessionService } from './session.service';

const WS_URL = 'ws://localhost:8000/api/ws';

@Injectable({
    providedIn: 'root'
})
export class ImageEditService implements OnDestroy {
    private socket!: WebSocket;

    private reconnectAttempts = 0;
    private readonly maxReconnectDelay = 30000; // 30s max wait
    private reconnectTimer: any;

    public channel = new Subject<ImageEditMessage>();
    public connected = new Subject<boolean>();
  
    constructor(private session: SessionService) { 
        this.scheduleReconnect();        
    }

    async send(msg: ImageEditMessage) {
        while (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
            await new Promise((resolve, reject) => {
                setInterval(() => {
                    resolve(null);
                }, 200);
            });
        }
        this.socket.send(JSON.stringify(msg));
    }

    connect() {
        if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
            return; // already connected or connecting
        }

        const storedId = this.session.getStoredSessionId();

        this.socket = new WebSocket(`${WS_URL}${storedId ? '?session_id=' + storedId : ''}`);

        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
            this.connected.next(true);
        };

        this.socket.onmessage = (msg) => {
            const data: ImageEditMessage = JSON.parse(msg.data);
            if (data.type === 'set_session') {
                this.session.storeSessionId(data['session_id']);
            } else {
                this.channel.next(data);
            }
        };

        this.socket.onclose = () => {
            console.log('WebSocket closed, retrying…');
            this.connected.next(false);
            this.scheduleReconnect();
        };

        this.socket.onerror = (err) => {
            console.error('WebSocket error', err);
            this.socket.close();
        };
    }

    private scheduleReconnect() {
        this.reconnectAttempts++;
        const delay = Math.min(1000 * 2 ** this.reconnectAttempts, this.maxReconnectDelay);
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = setTimeout(() => this.connect(), delay);
    }

    ngOnDestroy() {
        clearTimeout(this.reconnectTimer);
        this.socket?.close();
    }
}
