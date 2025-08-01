import { Component, AfterViewInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';

import { ImageEditService } from '../../../services/image-edit.service';
import { Waypoint } from '../../../models/waypoint';
import { HeaderComponent } from "../../../components/header/header/header.component";
import { MapEditComponent } from "../../../components/mapedit/map-edit/map-edit.component";

@Component({
    selector: 'app-step2-waypoints-edit',
    standalone: true,
    imports: [
        CommonModule,
        MatButtonModule,
        MatIconModule,
        FlexLayoutModule,
        HeaderComponent,
        MapEditComponent
    ],
    templateUrl: './step2-waypoints-edit.component.html',
    styleUrl: './step2-waypoints-edit.component.css'
})
export class Step2WaypointsEditComponent implements AfterViewInit, OnDestroy {
    subs: Subscription;
    @ViewChild(MapEditComponent) mapedit!: MapEditComponent;

    waypoints: Waypoint[] = [];

    constructor(public router: Router, private imgsrv: ImageEditService) {
        this.subs = imgsrv.channel.subscribe((msg) => {
            if (msg.type === 'waypoints-map') {
                this.mapedit.drawBackgroundImage(msg['image']);
                this.waypoints = msg['waypoints'].map((wp: any) => { 
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
            } else if (msg.type === "waypoints") {
                this.waypoints = msg['waypoints'].map((wp: any) => {
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
        });
    }

    ngAfterViewInit(): void {
        // initiate image load
        this.imgsrv.send({
            type: 'get-waypoints-map',
        });
    }

    ngOnDestroy(): void {
        // stop observers
        this.subs.unsubscribe();
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

    updateWaypoints() {
        this.imgsrv.send({
            type: 'update-wps',
            waypoints: this.waypoints.map((wp: Waypoint) => {
                return {
                    name: wp.name,
                    x: wp.x,
                    y: wp.y,
                }
            }),
        });
    }

    enumPoints(enumerate: (i: number, x: number, y: number) => boolean) {
        for (var i = 0; i < this.waypoints.length; i++) {
            const wp = this.waypoints[i];
            if (!enumerate(i, wp.x, wp.y)) {
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

    movePointTo(event: { i: number, x: number, y: number, callback: () => void }) {
        this.waypoints[event.i].x = event.x;
        this.waypoints[event.i].y = event.y;
        this.waypoints[event.i].lonlat_valid = false;
        event.callback();
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
