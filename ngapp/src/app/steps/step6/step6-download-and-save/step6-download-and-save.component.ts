import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';

import { HeaderComponent } from '../../../components/header/header/header.component';
import { MatButtonModule } from '@angular/material/button';
import { ImageEditService } from '../../../services/image-edit.service';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';

@Component({
    selector: 'app-step6-download-and-save',
    standalone: true,
    imports: [
        CommonModule,
        FlexLayoutModule,
        MatButtonModule,
        HeaderComponent,
    ],
    templateUrl: './step6-download-and-save.component.html',
    styleUrl: './step6-download-and-save.component.css'
})
export class Step6DownloadAndSaveComponent {

    subs: Subscription;
    
    constructor(private imgsrv: ImageEditService) {
        this.subs = imgsrv.channel.subscribe((msg) => {
            if (msg.type === 'docx' || msg.type === 'png') {                
                const blob = this.base64ToBlob(msg['data'], msg['mime']);
                this.downloadFile(msg['filename'], blob);
            } else if (msg.type === 'gpx' || msg.type === 'vfr') {
                const blob = new Blob([msg['data']], { type: msg['mime'] });
                this.downloadFile(msg['filename'], blob);
            }

        });
    }

    downloadDOCX() {
        this.imgsrv.send({
            type: 'get-docx'
        })
    }

    downloadVFR() {
        this.imgsrv.send({
            type: 'get-vfr'
        })
    }
    downloadGPX() {
        this.imgsrv.send({
            type: 'get-gpx'
        })
    }
    downloadPNG() {
        this.imgsrv.send({
            type: 'get-png'
        })
    }

    private base64ToBlob(base64: string, mime: string): Blob {
        const byteChars = atob(base64);
        const byteNumbers = new Array(byteChars.length);

        for (let i = 0; i < byteChars.length; i++) {
            byteNumbers[i] = byteChars.charCodeAt(i);
        }

        const byteArray = new Uint8Array(byteNumbers);
        return new Blob([byteArray], { type: mime });
    }

    private downloadFile(filename: string, blob: Blob) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.style.display = "none"; 
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

}
