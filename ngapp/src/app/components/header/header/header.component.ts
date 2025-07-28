import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { Router } from '@angular/router';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';

import { ImageEditService } from '../../../services/image-edit.service';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
    selector: 'app-header',
    standalone: true,
    imports: [
        MatButtonModule,
        MatIconModule,
        MatTooltipModule,
        FlexLayoutModule,
    ],
    templateUrl: './header.component.html',
    styleUrl: './header.component.css'
})
export class HeaderComponent {

    @Input('step-index') step_index: number = 0;
    @Input() title: string = '';
    @Input() tooltip: string = '';
    @Output('before-forward') before_forward = new EventEmitter();

    constructor(public router: Router, private imgsrv: ImageEditService) { }

    stepBack() {
        this.imgsrv.send({
            type: "step-back",
        }); // we don't need to wait for the answer
        this.router.navigateByUrl(`/step${this.step_index-1}`);
    }

    stepForward() {
        this.before_forward.emit();
        this.imgsrv.send({
            type: "step-forward",
        }); // we don't need to wait for the answer
        this.router.navigateByUrl(`/step${this.step_index+1}`);
    }

}
