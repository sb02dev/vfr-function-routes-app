import { Component, AfterViewInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ImageEditService } from '../../../services/image-edit.service';
import { HeaderComponent } from "../../../components/header/header/header.component";
import { MapEditComponent } from "../../../components/mapedit/map-edit/map-edit.component";

@Component({
  selector: 'app-step1-area-selection',
  standalone: true,
    imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    FlexLayoutModule,
    MatTooltipModule,
    HeaderComponent,
    MapEditComponent
],
  templateUrl: './step1-area-selection.component.html',
  styleUrl: './step1-area-selection.component.css'
})
export class Step1AreaSelectionComponent implements AfterViewInit, OnDestroy {
    
    subs: Subscription;
    @ViewChild(MapEditComponent) mapedit!: MapEditComponent;

    // area of interest edit variables
    rect: [number, number, number, number] = [100, 100, 200, 200];
    lonlat: [number, number, number, number] = [0, 0, 0, 0];

    constructor(public router: Router, private imgsrv: ImageEditService) {
        this.subs = imgsrv.channel.subscribe((msg) => {
            if (msg.type === 'area-of-interest') {
                this.rect = [
                    msg['top-left'].x,
                    msg['top-left'].y,
                    msg['bottom-right'].x - msg['top-left'].x,
                    msg['bottom-right'].y - msg['top-left'].y
                ];
                this.lonlat = [
                    msg['top-left'].lon,
                    msg['top-left'].lat,
                    msg['bottom-right'].lon,
                    msg['bottom-right'].lat
                ];
            }
        });
    }

    ngAfterViewInit(): void { 
        // initiate image load
        this.imgsrv.send({ type: 'get-area-of-interest' });
        this.imgsrv.send({ type: 'get-low-res-map' });
    }

    ngOnDestroy(): void {
        // stop observers
        this.subs.unsubscribe();
    }

    stepForward() {
        this.setAreaOfInterest();
    }

    enumPoints(enumerate: (i: number, map_coords: boolean, x: number, y: number, w: number | undefined, h: number | undefined) => boolean) {
        const [sx, sy, sw, sh] = this.rect;
        const xys = [[sx, sy], [sx + sw, sy], [sx + sw, sy + sh], [sx, sy + sh]];
        for (var i = 0; i < xys.length; i++) {
            const xy = xys[i];
            if (!enumerate(i, true, xy[0], xy[1], undefined, undefined)) {
                break;
            }
        }
    }

    movePointTo(event: { i: number, x: number, y: number, callback: () => void }) {
        const [x, y] = [event.x, event.y]; //this.mapedit.getCanvas2ImageCoords(event.x, event.y);
        const [sx, sy, sw, sh] = this.rect;
        if (event.i == 0) {
            this.rect = [x, y, sw - (x - sx), sh - (y - sy)];
        } else if (event.i == 1) {
            this.rect = [sx, y, x - sx, sh - (y - sy)];
        } else if (event.i == 2) {
            this.rect = [sx, sy, x - sx, y - sy];
        } else if (event.i == 3) {
            this.rect = [x, sy, sw - (x - sx), y - sy];
        }
        event.callback();
    }

    setAreaOfInterest() {
        this.imgsrv.send({
            type: 'set-area-of-interest',
            topleft: { x: this.rect[0], y: this.rect[1] },
            bottomright: { x: this.rect[0] + this.rect[2], y: this.rect[1] + this.rect[3] },
        });
    }

    drawOverlayTransformed(event: { canvas: HTMLCanvasElement, imgWidth: number, imgHeight: number }) {
        // get references and clear canvas
        const canvas = event.canvas;
        const ctx = canvas.getContext('2d')!;
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Mapping from data coords to image pixels
        const [sx, sy, sw, sh] = this.getRectImageCoords();

        // draw rectangle
        ctx.beginPath();
        ctx.lineWidth = 6;
        ctx.strokeStyle = "red";
        ctx.rect(sx, sy, sw, sh);        
        ctx.stroke();

        // draw corners
        const xys = [[sx, sy], [sx + sw, sy], [sx + sw, sy + sh], [sx, sy + sh]]
        for (var i = 0; i < xys.length; i++) {
            const xy = xys[i];
            ctx.beginPath();
            ctx.fillStyle = i==this.mapedit.selectedPoint?"green":"red";
            ctx.arc(xy[0], xy[1], 12, 0, 2*Math.PI);
            ctx.fill();
        }
    }

    private getRectImageCoords() {
        // Determine crop region in image space (sx, sy, sw, sh)
        const [rx, ry, rw, rh] = this.rect;
        const [x0, y0] = this.mapedit.getImage2CanvasCoords(rx, ry);
        const [x1, y1] = this.mapedit.getImage2CanvasCoords(rx + rw, ry + rh);

        return [x0, y0, x1-x0, y1-y0];
    }

}
