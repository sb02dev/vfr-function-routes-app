import { AfterViewInit, Component, OnDestroy, ViewChild } from '@angular/core';
import { Router } from '@angular/router';
import { MatIconModule } from "@angular/material/icon";
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { Subscription } from 'rxjs';

import { ImageEditService } from '../../../services/image-edit.service';
import { MapEditComponent } from "../../../components/mapedit/map-edit/map-edit.component";
import { CommonModule } from '@angular/common';
import { HeaderComponent } from '../../../components/header/header/header.component';
import { AnnLeg } from '../../../models/annotations'

@Component({
    selector: 'app-step4-annotations-edit',
    standalone: true,
    imports: [
        CommonModule,
        MatIconModule,
        FlexLayoutModule,
        MapEditComponent,
        HeaderComponent,
    ],
    templateUrl: './step4-annotations-edit.component.html',
    styleUrl: './step4-annotations-edit.component.css'
})
export class Step4AnnotationsEditComponent implements AfterViewInit, OnDestroy {

    subs: Subscription;

    legs: AnnLeg[] = [];
    leg_index: number = 0;
    
    @ViewChild(MapEditComponent) mapedit!: MapEditComponent;

    constructor(public router: Router, private imgsrv: ImageEditService) {
        this.subs = imgsrv.channel.subscribe((msg) => {
            if (msg.type === 'annotations-map') {
                this.mapedit.drawBackgroundImage(msg['image']);
                this.legs = msg['annotations'].map((leg: any) => {
                    return {
                        name: leg.name,
                        annotations: leg.annotations.map((ann: any) => {
                            return {
                                name: ann.name,
                                func_x: ann.func_x,
                                ofs_x: ann.ofs.x,
                                ofs_y: ann.ofs.y,
                            }
                        }),
                    }
                });
                this.leg_index = 0;
                this.changeLeg(0);
            } else if (msg.type === "annotations") {
                this.legs = msg['annotations'].map((leg: any) => {
                    return {
                        name: leg.name,
                        annotations: leg.annotations.map((ann: any) => {
                            return {
                                name: ann.name,
                                func_x: ann.func_x,
                                ofs_x: ann.ofs.x,
                                ofs_y: ann.ofs.y,
                            }
                        }),
                    }
                });
                this.changeLeg(0);
            }
        });
    }

    ngAfterViewInit(): void {
        // initiate image load
        this.imgsrv.send({
            type: 'get-annotations-map',
        });
    }

    ngOnDestroy(): void {
        // stop observers
        this.subs.unsubscribe();
    }

    changeLeg(increment: number) {
        let new_index = this.leg_index + increment;
        if (new_index >= this.legs.length) new_index = 0;
        if (new_index < 0) new_index = this.legs.length - 1;
        if (new_index >= 0 && new_index < this.legs.length) {
            this.leg_index = new_index;
        }
        this.mapedit.drawOverlayTransformed();
    }

    deleteAnnotation(index: number) {

    }

    change(prop: string, index: number, event: any) {

    }

}
