import { AfterContentInit, Component, ElementRef, OnDestroy, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatCardModule } from '@angular/material/card';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatCommonModule, provideNativeDateAdapter } from '@angular/material/core';
import { MatMenuModule } from '@angular/material/menu';
import { Router } from '@angular/router';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatSelectModule } from '@angular/material/select';

import { ImageEditService } from '../../../services/image-edit.service';
import { HeaderComponent } from '../../../components/header/header/header.component';


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
        MatMenuModule,
        MatSelectModule,
        ReactiveFormsModule,
        CommonModule,
        HeaderComponent
    ],
    providers: [provideNativeDateAdapter()],
    templateUrl: './step0-open-or-new.component.html',
    styleUrl: './step0-open-or-new.component.css'
})
export class Step0OpenOrNewComponent implements AfterContentInit {

    @ViewChild(HeaderComponent) header!: HeaderComponent;
    @ViewChild('file_selector') file_selector!: ElementRef<HTMLInputElement>;
    form: FormGroup;

    publishedRouteList: {id: number, name: string}[] = [];
    hasOpenRoute: boolean = false;
    mapsList: string[] = [];

    constructor(public router: Router, private fb: FormBuilder, private imgsrv: ImageEditService, private snackbar: MatSnackBar) {
        this.form = this.fb.group({
            rteName: [null, Validators.required],
            map: [null, Validators.required],
            speed: [90, Validators.required],
            dof: [null, Validators.required],
            tof: [null, Validators.required]
        });
        this.form.setValue({
            "rteName": "xxx",
            "map": "xxx",
            "speed": 100,
            "dof": new Date(2025, 8, 1, 7, 0),
            "tof": "07:00"
        });
    }

    ngAfterContentInit(): void {
        this.imgsrv.send('get-published-routes', this.gotPublishedRoutes.bind(this));
    }

    gotPublishedRoutes(result: { routes: {id: number, name: string}[], has_open_route: boolean, maps: string[]}) {
        this.publishedRouteList = result['routes'];
        this.hasOpenRoute = result['has_open_route'];
        this.mapsList = result['maps'];
    }


    editOpenRoute() {
        this.header.stepForward();
    }

    loadRoute() {
        let fs = this.file_selector.nativeElement;
        fs.onchange = null;
        fs.files = null;
        fs.onchange = async () => {
            if (fs.files && fs.files.length > 0) {
                let fstr = '';
                for (var i = 0; i < fs.files.length; i++) {
                    const fbuf = await fs.files[i].arrayBuffer()
                    fstr = String.fromCharCode(...new Uint8Array(fbuf)); // no base64 because it is JSON anyway
                    this.imgsrv.send('load', this.routeLoaded.bind(this), { data: fstr });
                    break; // don't upload multiple files
                };
            }
        }
        fs.click()
    }


    createRoute() {
        // just create an empty route
        const val = this.form.value;
        const dof = val.dof.getFullYear() + "-" + ("00" + (val.dof.getMonth()+1)).slice(-2) + "-" + ("00" + val.dof.getDate()).slice(-2) + "T" +
                    val.tof + ":00.000Z"
        this.imgsrv.send('create', this.routeLoaded.bind(this), {
            name: val.rteName,
            mapname: val.map,
            speed: val.speed,
            dof: dof
        })
    }


    loadSample() {
        // load sample route and go to its current step (last)
        this.imgsrv.send('sample', this.routeLoaded.bind(this));
    }

    publishedRoute(index: number) {
        // load sample route and go to its current step (last)
        this.imgsrv.send('load-published', this.routeLoaded.bind(this), index);
    }

    routeLoaded(result: any) {
        if (result['result'] === 'success') {
            this.snackbar.open('Route loaded', undefined, { duration: 5000, panelClass: 'snackbar-success' });
            // now we can go to the first step
            if (result['step']) {
                this.router.navigateByUrl(`/step${result['step']}`);
            } else {
                this.router.navigateByUrl('/step1');
            }
        } else if (result['result'] === 'failed') {
            this.snackbar.open('Load of route failed', undefined, { duration: 3000, panelClass: 'snackbar-error' });
        }
    }

    changeRouteData() {
        // pass, it is here just to avoid continuous refresh
    }

}  
