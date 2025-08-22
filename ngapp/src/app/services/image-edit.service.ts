import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Subject } from 'rxjs';
import { MatSnackBar } from '@angular/material/snack-bar';

import { environment } from '../../environments/environment';
import { ImageEditMessage } from '../models/image-edit-msg';
import { SessionService } from './session.service';


@Injectable({
    providedIn: 'root'
})
export class ImageEditService implements OnDestroy {
    private socket!: WebSocket;

    private reconnectAttempts = 0;
    private readonly maxReconnectDelay = 30000; // 30s max wait
    private reconnectTimer: any;

    public channel = new Subject<ImageEditMessage>();
    public binary_channel = new Subject<Blob>();
    public connected = new BehaviorSubject<boolean>(false);
    public communicating = new BehaviorSubject<boolean>(false);

    public expectedResponses = new Map<string, string[]>();
  
    constructor(private session: SessionService, private snackbar: MatSnackBar) { 
        this.scheduleReconnect();        
    }

    async send(msg: ImageEditMessage, expectedResponses: string[] = []) {
        if (expectedResponses.length != 0) {
            this.communicating.next(true);
            this.expectedResponses.set(msg.type, expectedResponses);
        }
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

        this.socket = new WebSocket(`${environment.WS_URL}${storedId ? '?session_id=' + storedId : ''}`);

        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
            this.connected.next(true);
        };

        this.socket.onmessage = (msg) => {
            if (typeof msg.data === 'string') {
                const data: ImageEditMessage = JSON.parse(msg.data);
                if (data.type === 'set_session') {
                    this.session.storeSessionId(data['session_id']);
                } else {
                    if (data.type === 'result' && data['result'] === 'exception') {
                        const msg = `SERVER ERROR: (${data['exception_type']}) ${data['message']}`;
                        console.error(msg, data['traceback']);
                        this.snackbar.open(
                            msg,
                            undefined,
                            { duration: 10000, panelClass: 'snackbar-error' }
                        );
                    }
                    this.communicating.next(this.checkCommunicating(data.type));
                    this.channel.next(data);
                }
            } else if (msg.data instanceof Blob) {
                this.communicating.next(this.checkCommunicating('--blob--'));
                const data: Blob = msg.data;
                this.binary_channel.next(data);
            }
        };

        this.socket.onclose = () => {
            console.log('WebSocket closed, retrying…');
            this.connected.next(false);
            this.scheduleReconnect();
        };

        this.socket.onerror = (err) => {
            console.error('WebSocket error', err);
            this.connected.next(false);
            this.socket.close();
        };
    }

    private checkCommunicating(response: string): boolean {
        // will cancel all that expects this response
        let tocancel: string[] = [];
        this.expectedResponses.forEach((resps, key) => {
            if (resps.indexOf(response) != -1) {
                tocancel.push(key);
            }
        })
        tocancel.forEach((key) => {
            this.expectedResponses.delete(key);
        })
        return this.expectedResponses.size > 0;
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
