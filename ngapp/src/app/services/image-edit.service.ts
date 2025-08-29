import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Subject } from 'rxjs';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router } from '@angular/router';
import { io, Socket } from 'socket.io-client';

import { environment } from '../../environments/environment';
import { ImageEditMessage } from '../models/image-edit-msg';
import { SessionService } from './session.service';


@Injectable({
    providedIn: 'root'
})
export class ImageEditService implements OnDestroy {
    private socketio: Socket;

    public connected = new BehaviorSubject<boolean>(false);
    public communicating = new BehaviorSubject<boolean>(false);
    private commcount = 0;

    constructor(private router: Router, private session: SessionService, private snackbar: MatSnackBar) { 
        const storedId = this.session.getStoredSessionId();
        this.socketio = io('http://localhost:8000', {
            transports: ['websocket', 'polling'], // enable fallbacks
            path: "/socket.io",
            auth: { session_id: storedId },
            withCredentials: true,
        });
        this.socketio.on('connect', () => {
            this.connected.next(true);
        });
        this.socketio.on('disconnect', (reason) => {
            this.connected.next(false);
            console.log(reason);
        });
        this.socketio.on("connect_error", (err: Error) => {
            console.error("🚫 Connection rejected:", err.message);
            // If your server rejects with a reason:
            // (e.g. socket.io(server).use((socket,next)=>next(new Error("unauthorized"))))
            // you get that string here as err.message
            if (err.cause === 1008) { // TODO: test it
                console.log('WebSocket rejected, retrying…');
                this.snackbar.open(
                    "Server has reached the maximum session limit. Please wait until another user finishes work and retry.",
                    undefined,
                    { duration: 10000, panelClass: 'snackbar-error' }
                );
                if (!this.router.isActive('/step0', { paths: 'subset', queryParams: 'ignored', fragment: 'ignored', matrixParams: 'ignored' })) {
                    this.router.navigateByUrl('/step0');
                }
                // TODO: schedule reconnect
                //this.reconnectAttempts = this.lastReconnectAttempts;
            } else {
                console.log('WebSocket closed, ');
            }
        });
        this.socketio.on('error', (err) => {
            console.error('SocketIO error', err);
            this.connected.next(false);
            this.socketio.close();
        });
        this.socketio.on('set_session', (data: any) => {
            this.session.storeSessionId(data['session_id']);
        });
        this.socketio.on('result', (data: any) => {
            if (data['result'] === 'exception') {
                const msg = `SERVER ERROR: (${data['exception_type']}) ${data['message']}`;
                console.error(msg, data['traceback']);
                this.snackbar.open(
                    msg,
                    undefined,
                    { duration: 10000, panelClass: 'snackbar-error' }
                );
            }
        });
    }

    async send(event_type: string, callback?: (...responses: any[]) => void, ...args: any[]) {
        this.communicating.next(true);
        this.commcount++;
        this.socketio.emit(event_type, ...args, (...responses: any[]) => {
            this.commcount--;
            if (this.commcount <= 0) {
                this.communicating.next(false);
            }
            if (callback) {
                callback(...responses);
            }
        });
    }

    onSocketIO<T>(event: string, listener: (msg: T) => void) {
        this.socketio.on(event, listener);
    }

    offSocketIO<T>(event: string, listener: (msg: T) => void) {
        this.socketio.off(event, listener);
    }

    ngOnDestroy() {
        this.socketio.close();
    }
}
