import { AfterViewInit, Component, EventEmitter, Input, Output } from '@angular/core';
import { MatCommonModule } from '@angular/material/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { BehaviorSubject, Subscription } from 'rxjs';

import { ImageEditService } from '../../../services/image-edit.service';
import { ImageEditMessage } from '../../../models/image-edit-msg';

@Component({
    selector: 'app-header',
    standalone: true,
    imports: [
        CommonModule,
        MatCommonModule,
        MatButtonModule,
        MatIconModule,
        MatTooltipModule,
        MatProgressSpinnerModule,
        FlexLayoutModule,
    ],
    templateUrl: './header.component.html',
    styleUrl: './header.component.css'
})
export class HeaderComponent implements AfterViewInit {

    public isFullScreen$ = new BehaviorSubject<boolean>(false);
    public allow_next = true;

    @Input('step-index') step_index: number = 0;
    @Input() header_title: string = '';
    @Input() tooltip: string = '';
    @Output('before-forward') before_forward = new EventEmitter();
    @Input('last-step') last_step: boolean = false;
    @Input('first-step') first_step: boolean = false;

    constructor(public router: Router, public imgsrv: ImageEditService, private snackbar: MatSnackBar) { 
    }

    ngAfterViewInit(): void {
        document.addEventListener("fullscreenchange", (event) => {
            if (document.fullscreenElement) {
                this.isFullScreen$.next(true);
            } else {
                this.isFullScreen$.next(false);
            }
        });
    }

    gotResult(result: ImageEditMessage) {
        if (result['result'] === 'success') {
            // nothing to do here
        } else if (result['result'] === 'invalid-step-value') {
            this.snackbar.open('Entering next step of route editing failed: invalid step', undefined, { duration: 3000, panelClass: 'snackbar-error' });
        } else if (result['result'] === 'no-route') {
            this.snackbar.open('There is no route open on the server', undefined, { duration: 3000, panelClass: 'snackbar-error' });
            this.router.navigateByUrl('/step0');
        }
    }

    stepBack() {
        this.imgsrv.send("step", (result: ImageEditMessage) => {
            this.gotResult(result);
            this.router.navigateByUrl(`/step${this.step_index - 1}`);
        }, {
            step: this.step_index-1,
        }); 
    }

    stepForward() {
        this.before_forward.emit();
        this.imgsrv.send("step", (result: ImageEditMessage) => {
            this.gotResult(result);
            this.router.navigateByUrl(`/step${this.step_index + 1}`);
        }, {
            step: this.step_index+1,
        }); 
    }

    goFullScreen() {
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else {
            document.body.requestFullscreen();
        }
    }
}
