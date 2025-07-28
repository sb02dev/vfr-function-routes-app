import { Component, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatCardModule } from '@angular/material/card';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatCommonModule, provideNativeDateAdapter } from '@angular/material/core';
import { Router } from '@angular/router';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { ImageEditService } from '../../../services/image-edit.service';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';

@Component({
    selector: 'app-step0-open-or-new',
    standalone: true,
    imports: [
        MatButtonModule,
        FlexLayoutModule,
        MatFormFieldModule,
        MatInputModule,
        MatCardModule,
        MatDatepickerModule,
        MatCommonModule,
        ReactiveFormsModule,
        CommonModule
    ],
    providers: [provideNativeDateAdapter()],
    templateUrl: './step0-open-or-new.component.html',
    styleUrl: './step0-open-or-new.component.css'
})
export class Step0OpenOrNewComponent {
    @ViewChild('file_selector') file_selector!: ElementRef<HTMLInputElement>;
    form: FormGroup;

    constructor(public router: Router, private fb: FormBuilder, private imgsrv: ImageEditService) {
        this.form = this.fb.group({
            rteName: [null, Validators.required],
            speed: [90, Validators.required],
            dof: [null, Validators.required],
            tof: [null, Validators.required]
        });
    }


    loadRoute() {
        // TODO: upload from JSON file
        let fs = this.file_selector.nativeElement;
        fs.onchange = null;
        fs.files = null;
        fs.onchange = async () => {
            if (fs.files && fs.files.length>0) {
                for (var i = 0; i < fs.files.length; i++) {
                    const fbuf = await fs.files[i].arrayBuffer()
                    const fstr = String.fromCharCode(...new Uint8Array(fbuf)); // no base64 because it is JSON anyway
                    this.imgsrv.send({
                        type: 'load',
                        data: fstr
                    });
                    break; // don't upload multiple files
                };
                // jump to its current step
                this.router.navigateByUrl('/step1')
            }
        }
        fs.click()
    }


    createRoute() {
        // just create an empty route
        const val = this.form.value;
        const dof = val.dof.getFullYear() + "-" + ("00" + val.dof.getMonth()).slice(-2) + "-" + ("00" + val.dof.getDay()).slice(-2) + "T" +
                    val.tof + ":00.000Z"
        this.imgsrv.send({
            type: 'create',
            name: val.rteName,
            speed: val.speed,
            dof: dof
        })
        // jump to its current step (first)
        this.router.navigateByUrl('/step1');
    }


    loadSample() {
        // load sample route and go to its current step (last)
        this.imgsrv.send({
            type: 'sample'
        })
        this.router.navigateByUrl('/step1');
    }
}  
