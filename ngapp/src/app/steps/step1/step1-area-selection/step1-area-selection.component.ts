import { Component, AfterContentInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { MatCardModule } from '@angular/material/card';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatTableModule } from '@angular/material/table';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Router } from '@angular/router';

import { ImageEditService } from '../../../services/image-edit.service';
import { HeaderComponent } from "../../../components/header/header/header.component";
import { MapEditComponent } from "../../../components/mapedit/map-edit/map-edit.component";
import { LonLatEditDialogComponent } from '../../../components/lonlateditdlg/lon-lat-edit-dialog/lon-lat-edit-dialog.component';

@Component({
    selector: 'app-step1-area-selection',
    standalone: true,
    imports: [
        CommonModule,
        MatButtonModule,
        MatIconModule,
        FlexLayoutModule,
        MatTooltipModule,
        MatCardModule,
        MatTableModule,
        HeaderComponent,
        MapEditComponent,
],
  templateUrl: './step1-area-selection.component.html',
  styleUrl: './step1-area-selection.component.css'
})
export class Step1AreaSelectionComponent implements AfterContentInit {
    
    @ViewChild(MapEditComponent) mapedit!: MapEditComponent;
    @ViewChild(HeaderComponent) header!: HeaderComponent;

    // area of interest edit variables
    rect: [number, number, number, number] = [100, 100, 200, 200];
    lonlat: [number, number, number, number] = [0, 0, 0, 0];
    lonlatValid: [boolean, boolean] = [false, false];

    // size status
    status: string = 'ok';

    constructor(public router: Router, private imgsrv: ImageEditService, private dialog: MatDialog, private snackbar: MatSnackBar) {
    }

    ngAfterContentInit(): void { 
        // initiate image load
        this.imgsrv.send('get-area-of-interest', this.gotAreaOfInterest.bind(this));
        this.imgsrv.send('get-low-res-map', (result) => { this.mapedit.gotTiledImage(result) });
    }

    gotAreaOfInterest(result: any) {
        this.rect = [
            result['top-left'].x,
            result['top-left'].y,
            result['bottom-right'].x - result['top-left'].x,
            result['bottom-right'].y - result['top-left'].y
        ];
        this.lonlat = [
            result['top-left'].lon,
            result['top-left'].lat,
            result['bottom-right'].lon,
            result['bottom-right'].lat
        ];
        this.lonlatValid[0] = true;
        this.lonlatValid[1] = true;
        this.mapedit.drawOverlayTransformed();
        this.status = result['status'];
        if (result['status'] == 'ok') {
            this.header.allow_next = true;
        } else if (result['status'] == 'warning') {
            this.header.allow_next = true;
            this.snackbar.open('WARNING: Area may be too large to create the final image/document', undefined, { duration: 3000, panelClass: 'snackbar-warning' });
        } else if (result['status'] == 'error') {
            this.header.allow_next = false;
            this.snackbar.open('ERROR: Area is too large to create the final image/document', undefined, { duration: 3000, panelClass: 'snackbar-error' });
        }
    }

    stepForward() {
        this.setAreaOfInterest();
    }

    editLonLatDialog(index:number, corner: {name: string, lon: number, lat: number}) {
        const dialogRef = this.dialog.open(LonLatEditDialogComponent, {
            data: {"lon": corner.lon, "lat": corner.lat}
        });

        dialogRef.afterClosed().subscribe(result => {
            if (result.save) {
                if (index == 0) { // top-left
                    this.lonlat = [result.lon, result.lat, this.lonlat[2], this.lonlat[3]];
                    this.lonlatValid[0] = false;
                } else if (index == 2) { // bottom-right
                    this.lonlat = [this.lonlat[0], this.lonlat[1], result.lon, result.lat];
                    this.lonlatValid[1] = false;
                }
                this.setAreaOfInterest(true);
            }
        });
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
        if (event.i == 0) { // top-left
            this.rect = [x, y, sw - (x - sx), sh - (y - sy)];
            this.lonlatValid[0] = false;
        } else if (event.i == 1) { // top-right -> moves both
            this.rect = [sx, y, x - sx, sh - (y - sy)];
            this.lonlatValid[0] = false;
            this.lonlatValid[1] = false;
        } else if (event.i == 2) { // bottom-right
            this.rect = [sx, sy, x - sx, y - sy];
            this.lonlatValid[1] = false;
        } else if (event.i == 3) { // bottom-left -> moves both
            this.rect = [x, sy, sw - (x - sx), y - sy];
            this.lonlatValid[0] = false;
            this.lonlatValid[1] = false;
        }
        event.callback();
    }

    setAreaOfInterest(byLonLat: boolean = false) {
        if (!byLonLat) {
            this.imgsrv.send('set-area-of-interest', this.gotAreaOfInterest.bind(this), {
                topleft: { x: this.rect[0], y: this.rect[1] },
                bottomright: { x: this.rect[0] + this.rect[2], y: this.rect[1] + this.rect[3] },
            });
        } else {
            this.imgsrv.send('set-area-of-interest', this.gotAreaOfInterest.bind(this), {
                topleft: { lon: this.lonlat[0], lat: this.lonlat[1] },
                bottomright: { lon: this.lonlat[2], lat: this.lonlat[3] },
            });
        }
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
