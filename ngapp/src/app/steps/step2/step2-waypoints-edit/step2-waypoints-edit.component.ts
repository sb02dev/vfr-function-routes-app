import { Component, AfterContentInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { MatTableModule } from '@angular/material/table';
import { MatCardModule } from "@angular/material/card";
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDialog } from '@angular/material/dialog';
import { Router } from '@angular/router';

import { ImageEditService } from '../../../services/image-edit.service';
import { Waypoint } from '../../../models/waypoint';
import { HeaderComponent } from "../../../components/header/header/header.component";
import { MapEditComponent } from "../../../components/mapedit/map-edit/map-edit.component";
import { LonLatEditDialogComponent } from '../../../components/lonlateditdlg/lon-lat-edit-dialog/lon-lat-edit-dialog.component';
import { ImageEditMessage } from '../../../models/image-edit-msg';

@Component({
    selector: 'app-step2-waypoints-edit',
    standalone: true,
    imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
    FlexLayoutModule,
    MatTableModule,
    HeaderComponent,
    MapEditComponent,
    MatCardModule,
],
    templateUrl: './step2-waypoints-edit.component.html',
    styleUrl: './step2-waypoints-edit.component.css'
})
export class Step2WaypointsEditComponent implements AfterContentInit {

    @ViewChild(MapEditComponent) mapedit!: MapEditComponent;

    waypoints: Waypoint[] = [];

    constructor(public router: Router, private imgsrv: ImageEditService, private dialog: MatDialog) {
    }

    ngAfterContentInit(): void {
        // initiate image load
        this.imgsrv.send('get-waypoints', this.gotWaypoints.bind(this));
        this.imgsrv.send('get-waypoints-map', (result) => { this.mapedit.gotTiledImage(result) });
    }

    gotWaypoints(result: ImageEditMessage) {
        this.waypoints = result['waypoints'].map((wp: any) => {
            return {
                name: wp.name,
                x: wp.x,
                y: wp.y,
                lon: wp.lon,
                lat: wp.lat,
                lonlat_valid: true,
            }
        });
        this.mapedit.drawOverlayTransformed();
    }

    deleteWaypoint(index: number) {
        this.waypoints.splice(index, 1);
        this.updateWaypoints();
        this.mapedit.drawOverlayTransformed();
    }

    moveWaypoint(index: number, up: boolean) {
        let move = up ? -1 : 1;
        this.waypoints.splice(index + move, 0, this.waypoints.splice(index, 1)[0]);
        this.updateWaypoints();
        this.mapedit.drawOverlayTransformed();
    }

    renameWaypoint(index: number, event: Event) {
        if (!event.target) return;
        let target = (event.target as HTMLInputElement);
        if (!target.value) return;
        this.waypoints[index].name = target.value;
        this.updateWaypoints();
        this.mapedit.drawOverlayTransformed();
    }

    editLonLatDialog(index: number, wp: Waypoint) {
        const dialogRef = this.dialog.open(LonLatEditDialogComponent, {
            data: {"lon": wp.lon, "lat": wp.lat}
        });

        dialogRef.afterClosed().subscribe(result => {
            if (result.save) {
                this.waypoints[index].lon = result.lon;
                this.waypoints[index].lat = result.lat;
                this.waypoints[index].lonlat_valid = false;
                this.updateWaypoints(true);
            }
        });
    }

    updateWaypoints(byLonLat: boolean = false) {
        if (!byLonLat) {
            this.imgsrv.send('update-wps', this.gotWaypoints.bind(this), {
                waypoints: this.waypoints.map((wp: Waypoint) => {
                    return {
                        name: wp.name,
                        x: wp.x,
                        y: wp.y,
                    }
                }),
            });
        } else {
            this.imgsrv.send('update-wps', this.gotWaypoints.bind(this), {
                waypoints: this.waypoints.map((wp: Waypoint) => {
                    return {
                        name: wp.name,
                        lon: wp.lon,
                        lat: wp.lat,
                    }
                }),
            });
        }
    }

    enumPoints(enumerate: (i: number, map_coords: boolean, x: number, y: number, w: number | undefined, h: number | undefined) => boolean) {
        for (var i = 0; i < this.waypoints.length; i++) {
            const wp = this.waypoints[i];
            if (!enumerate(i, true, wp.x, wp.y, undefined, undefined)) {
                break;
            }
        }
    }

    addPointAt(event: { x: number, y: number, callback: () => void }) {
        this.waypoints.push({
            name: '???',
            x: event.x,
            y: event.y,
            lon: 0,
            lat: 0,
            lonlat_valid: false
        });
        event.callback();
        this.updateWaypoints();
    }

    addPointAtLonLat() {
        const dialogRef = this.dialog.open(LonLatEditDialogComponent, {
            data: { "lon": this.waypoints[0].lon, "lat": this.waypoints[0].lat }
        });

        dialogRef.afterClosed().subscribe(result => {
            if (result.save) {
                this.waypoints.push({
                    name: '???',
                    x: 0,
                    y: 0,
                    lon: result.lon,
                    lat: result.lat,
                    lonlat_valid: false
                });
                this.updateWaypoints(true);
            }
        });
    }

    movePointTo(event: { i: number, x: number, y: number, callback: () => void }) {
        this.waypoints[event.i].x = event.x;
        this.waypoints[event.i].y = event.y;
        this.waypoints[event.i].lonlat_valid = false;
        event.callback();
    }

    compareWaypoints(index: number, wp: Waypoint) {
        return index;
    }

    drawOverlayTransformed(event: { canvas: HTMLCanvasElement, imgWidth: number, imgHeight: number }) {
        // get references and clear canvas
        const canvas = event.canvas;
        const ctx = canvas.getContext('2d')!;
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        if (this.waypoints.length > 0) {
            // draw polygon
            const [x, y] = this.mapedit.getImage2CanvasCoords(this.waypoints[0].x, this.waypoints[0].y);
            ctx.beginPath();
            ctx.moveTo(x, y);
            for (let i = 1; i < this.waypoints.length; i++) {
                const [x, y] = this.mapedit.getImage2CanvasCoords(this.waypoints[i].x, this.waypoints[i].y);
                ctx.lineTo(x, y);
            }
            ctx.closePath();
            ctx.lineWidth = 6;
            ctx.strokeStyle = "red";
            ctx.stroke();

            // draw corners and names
            for (let i = 0; i < this.waypoints.length; i++) {
                const wp = this.waypoints[i]
                const [x, y] = this.mapedit.getImage2CanvasCoords(wp.x, wp.y);
                ctx.beginPath();
                ctx.fillStyle = i == this.mapedit.selectedPoint ? "green" : "red";
                ctx.arc(x, y, 12, 0, 2 * Math.PI);
                ctx.fill();
                ctx.font = "12px serif";
                ctx.fillText(wp.name, x+15, y);
            }
        }
    }

}
