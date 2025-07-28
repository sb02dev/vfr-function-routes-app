import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

import { ImageEditMessage } from '../models/image-edit-msg';

@Injectable({
    providedIn: 'root'
})
export class ImageEditService {
    socket!: WebSocket;

    channel = new Subject<ImageEditMessage>();
  
    constructor() { 
        this.socket = new WebSocket("ws://localhost:8000/api/ws");
        this.socket.onopen = () => {
            //this.socket.send(JSON.stringify({ event: 'init' }));
        };
        this.socket.onmessage = (msg) => {
            const data: ImageEditMessage = JSON.parse(msg.data);
            this.channel.next(data);
        };
    }

    async send(msg: ImageEditMessage) {
        while (this.socket.readyState !== WebSocket.OPEN) {
            await new Promise((resolve, reject) => {
                setInterval(() => {
                    resolve(null);
                }, 200);
            });
        }
        this.socket.send(JSON.stringify(msg));
    }

}
