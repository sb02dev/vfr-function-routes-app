import { AfterContentInit, Component, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { provideNativeDateAdapter } from '@angular/material/core';
import { ReactiveFormsModule, FormsModule, FormGroup, FormBuilder, Validators } from '@angular/forms';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar } from '@angular/material/snack-bar';

import { HeaderComponent } from '../../../components/header/header/header.component';
import { ImageEditService } from '../../../services/image-edit.service';
import { ImageEditMessage } from '../../../models/image-edit-msg';

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
export class Step6DownloadAndSaveComponent implements AfterContentInit {

    form: FormGroup;

    dof: Date = new Date();
    tof: string = "00:00:00";

    private pendingMeta: any = null;

    constructor(private imgsrv: ImageEditService, private fb: FormBuilder, private snackbar: MatSnackBar) {
        this.form = this.fb.group({
            rteName: [null, Validators.required],
            speed: [90, Validators.required],
            dof: [null, Validators.required],
            tof: [null, Validators.required]
        });        
    }

    ngAfterContentInit(): void {
        this.imgsrv.send('get-route-data', this.gotRouteData.bind(this));
    }

    gotRouteData(result: ImageEditMessage) {
        this.dof = new Date(result['dof']);
        this.tof = ("00" + this.dof.getUTCHours()).slice(-2) + ":" + ("00" + this.dof.getUTCMinutes()).slice(-2) + ":" + ("00" + this.dof.getUTCSeconds()).slice(-2);
        this.form.patchValue({
            rteName: result['name'],
            speed: result['speed'],
            dof: this.dof,
            tof: this.tof,
        });
    }

    changeRouteData() {
        const val = this.form.value;
        this.dof = val['dof'];
        this.tof = val['tof'];
        const dofs = this.dof.getFullYear() + "-" + ("00" + (this.dof.getMonth()+1)).slice(-2) + "-" + ("00" + this.dof.getDate()).slice(-2) + "T" +
            this.tof + ".000Z"
        this.imgsrv.send('set-route-data', this.gotRouteData.bind(this), {
            name: val['rteName'],
            speed: val['speed'],
            dof: dofs,
        })
    }

    downloadDOCX() { this.imgsrv.send('get-docx', this.gotFileAsBinary.bind(this)); }
    downloadVFR() { this.imgsrv.send('get-vfr', this.gotFileAsText.bind(this)); }
    downloadGPX() { this.imgsrv.send('get-gpx', this.gotFileAsText.bind(this)); }
    downloadPNG() { this.imgsrv.send('get-png', this.gotFileAsBinary.bind(this)); }
    saveToServer() { this.imgsrv.send('save-to-cloud', this.gotSaveToCloudResult.bind(this)); }

    gotSaveToCloudResult(result: ImageEditMessage) {
        if (result['result'] === 'success') {
            this.snackbar.open(`Route saved on server (name: ${result['fname']})`, undefined, { duration: 5000, panelClass: 'snackbar-success' });
        } else if (result['result'] === 'fail') {
            this.snackbar.open('Save of route on server failed', undefined, { duration: 3000, panelClass: 'snackbar-error' });
        } else if (result['result'] === 'filename-already-exists') {
            this.snackbar.open('Cannot save, this name already exists', undefined, { duration: 3000, panelClass: 'snackbar-error' });
        } else if (result['result'] === 'too-many-files') {
            this.snackbar.open('Did not save! Too many published routes, contact the system administrator', undefined, { duration: 3000, panelClass: 'snackbar-error' });
        } else if (result['result'] === 'no-route') {
            this.snackbar.open('No route open on server', undefined, { duration: 3000, panelClass: 'snackbar-warning' });
        }
    }

    gotFileAsText(result: ImageEditMessage) {
        const blob = new Blob([result['data']], { type: result['mime'] });
        this.downloadFile(result['filename'], blob);
    }

    gotFileAsBinary(meta: ImageEditMessage, file: BlobPart) {
        const blob = new Blob([file], { type: meta['mime'] });
        this.downloadFile(meta['filename'], blob);
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
