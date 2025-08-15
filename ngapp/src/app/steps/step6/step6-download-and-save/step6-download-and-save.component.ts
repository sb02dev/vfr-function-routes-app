import { AfterViewInit, Component, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { provideNativeDateAdapter } from '@angular/material/core';
import { ReactiveFormsModule, FormsModule, FormGroup, FormBuilder, Validators } from '@angular/forms';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar } from '@angular/material/snack-bar';
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
        MatInputModule,
        HeaderComponent,
    ],
    providers: [provideNativeDateAdapter()],
    templateUrl: './step6-download-and-save.component.html',
    styleUrl: './step6-download-and-save.component.css'
})
export class Step6DownloadAndSaveComponent implements AfterViewInit, OnDestroy {

    subs: Subscription;
    binary_subs: Subscription;

    form: FormGroup;

    dof: Date = new Date();
    tof: string = "00:00:00";

    private pendingMeta: any = null;

    constructor(private imgsrv: ImageEditService, private fb: FormBuilder, private snackbar: MatSnackBar) {
        this.subs = imgsrv.channel.subscribe((msg) => {
            if (msg.type === 'docx' || msg.type === 'png') {                
                this.pendingMeta = msg;
            } else if (msg.type === 'gpx' || msg.type === 'vfr') {
                const blob = new Blob([msg['data']], { type: msg['mime'] });
                this.downloadFile(msg['filename'], blob);
            } else if (msg.type === 'route-data') {
                this.dof = new Date(msg['dof']);
                this.tof = ("00" + this.dof.getUTCHours()).slice(-2) + ":" + ("00" + this.dof.getUTCMinutes()).slice(-2) + ":" + ("00" + this.dof.getUTCSeconds()).slice(-2);
                this.form.patchValue({
                    rteName: msg['name'],
                    speed: msg['speed'],
                    dof: this.dof,
                    tof: this.tof,
                });
            } else if (msg.type === 'save-to-cloud-result') {
                if (msg['result'] === 'success') {
                    this.snackbar.open(`Route saved on server (name: ${msg['fname']})`, undefined, { duration: 5000, panelClass: 'snackbar-success' });
                } else if (msg['result'] === 'fail') {
                    this.snackbar.open('Save of route on server failed', undefined, { duration: 3000, panelClass: 'snackbar-error' });
                } else if (msg['result'] === 'too-many-files') {
                    this.snackbar.open('Did not save! Too many published routes, contact the system administrator', undefined, { duration: 3000, panelClass: 'snackbar-error' });
                } else if (msg['result'] === 'no-route') {
                    this.snackbar.open('No route open on server', undefined, { duration: 3000, panelClass: 'snackbar-warning' });
                }
            }
        });
        this.binary_subs = imgsrv.binary_channel.subscribe((msg: Blob) => {
            if (this.pendingMeta) {
                this.downloadFile(this.pendingMeta['filename'], msg);
            }
        });
        this.form = this.fb.group({
            rteName: [null, Validators.required],
            speed: [90, Validators.required],
            dof: [null, Validators.required],
            tof: [null, Validators.required]
        });        
    }

    ngAfterViewInit(): void {
        this.imgsrv.send({ type: 'get-route-data' });
    }

    ngOnDestroy(): void {
        this.subs.unsubscribe();
        this.binary_subs.unsubscribe();
    }

    changeRouteData() {
        const val = this.form.value;
        this.dof = val['dof'];
        this.tof = val['tof'];
        const dofs = this.dof.getFullYear() + "-" + ("00" + (this.dof.getMonth()+1)).slice(-2) + "-" + ("00" + this.dof.getDate()).slice(-2) + "T" +
            this.tof + ".000Z"
        this.imgsrv.send({
            type: 'set-route-data',
            name: val['rteName'],
            speed: val['speed'],
            dof: dofs,
        })
    }

    downloadDOCX() { this.imgsrv.send({ type: 'get-docx' }); }
    downloadVFR() { this.imgsrv.send({ type: 'get-vfr' }); }
    downloadGPX() { this.imgsrv.send({ type: 'get-gpx' }); }
    downloadPNG() { this.imgsrv.send({ type: 'get-png' }); }
    saveToServer() { this.imgsrv.send({ type: 'save-to-cloud' }); }

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
