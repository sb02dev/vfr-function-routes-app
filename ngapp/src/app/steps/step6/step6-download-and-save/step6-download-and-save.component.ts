import { AfterViewInit, Component, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { provideNativeDateAdapter } from '@angular/material/core';
import { ReactiveFormsModule, FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { Subscription } from 'rxjs';

import { HeaderComponent } from '../../../components/header/header/header.component';
import { ImageEditService } from '../../../services/image-edit.service';

@Component({
    selector: 'app-step6-download-and-save',
    standalone: true,
    imports: [
        CommonModule,
        FlexLayoutModule,
        MatFormFieldModule,
        MatDatepickerModule,
        MatButtonModule,
        FormsModule,
        ReactiveFormsModule,
        HeaderComponent,
    ],
    providers: [provideNativeDateAdapter()],
    templateUrl: './step6-download-and-save.component.html',
    styleUrl: './step6-download-and-save.component.css'
})
export class Step6DownloadAndSaveComponent implements AfterViewInit, OnDestroy {

    subs: Subscription;
    binary_subs: Subscription;

    dof: Date = new Date();
    tof: string = "00:00:00";

    private pendingMeta: any = null;

    constructor(private imgsrv: ImageEditService) {
        this.subs = imgsrv.channel.subscribe((msg) => {
            if (msg.type === 'docx' || msg.type === 'png') {                
                this.pendingMeta = msg;
            } else if (msg.type === 'gpx' || msg.type === 'vfr') {
                const blob = new Blob([msg['data']], { type: msg['mime'] });
                this.downloadFile(msg['filename'], blob);
            } else if (msg.type === 'dof') {
                this.dof = new Date(msg['dof']);
                this.tof = ("00" + this.dof.getUTCHours()).slice(-2) + ":" + ("00" + this.dof.getUTCMinutes()).slice(-2) + ":" + ("00" + this.dof.getUTCSeconds()).slice(-2);
            }
        });
        this.binary_subs = imgsrv.binary_channel.subscribe((msg: Blob) => {
            if (this.pendingMeta) {
                this.downloadFile(this.pendingMeta['filename'], msg);
            }
        })
    }

    ngAfterViewInit(): void {
        this.imgsrv.send({ type: 'get-dof' });
    }

    ngOnDestroy(): void {
        this.subs.unsubscribe();
        this.binary_subs.unsubscribe();
    }

    changeDOF() {
        const dofs = this.dof.getFullYear() + "-" + ("00" + (this.dof.getMonth()+1)).slice(-2) + "-" + ("00" + this.dof.getDate()).slice(-2) + "T" +
            this.tof + ".000Z"
        this.imgsrv.send({
            type: 'set-dof',
            dof: dofs,
        })
    }

    downloadDOCX() { this.imgsrv.send({ type: 'get-docx' }); }
    downloadVFR() { this.imgsrv.send({ type: 'get-vfr' }); }
    downloadGPX() { this.imgsrv.send({ type: 'get-gpx' }); }
    downloadPNG() { this.imgsrv.send({ type: 'get-png' }); }

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
