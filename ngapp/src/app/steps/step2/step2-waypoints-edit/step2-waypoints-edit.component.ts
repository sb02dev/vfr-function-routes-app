import { Component, AfterViewInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DecimalPipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ImageEditService } from '../../../services/image-edit.service';
import { Waypoint } from '../../../models/waypoint';

@Component({
    selector: 'app-step2-waypoints-edit',
    standalone: true,
    imports: [
        CommonModule,
        DecimalPipe,
        MatButtonModule,
        MatIconModule,
        FlexLayoutModule,
        MatTooltipModule
    ],
    templateUrl: './step2-waypoints-edit.component.html',
    styleUrl: './step2-waypoints-edit.component.css'
})
export class Step2WaypointsEditComponent implements AfterViewInit, OnDestroy {
    @ViewChild('bgCanvas', { static: true }) bgCanvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('overlayCanvas', { static: true }) overlayCanvasRef!: ElementRef<HTMLCanvasElement>;
    private bgResize!: ResizeObserver;
    subs: Subscription;
    baseImage: HTMLImageElement | null = null;
    public selectedTool: string = 'panzoom';

    // pan and zoom variables
    private xlim: [number, number] = [0, 4];
    private ylim: [number, number] = [0, 4];
    private panStart: { x: number, y: number } | null = null;
    private zoomFactor: number = 1.1; // how much to zoom in/out per scroll step

    // waypoint edit variables
    waypoints: Waypoint[] = [];
    private selectionDistance: number = 10.;
    selectedPoint: number | null = null;

    constructor(public router: Router, private imgsrv: ImageEditService) {
        this.subs = imgsrv.channel.subscribe((msg) => {
            if (msg.type === 'high-res') {
                this.drawBackgroundImage(msg['image']);
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
                this.drawOverlayTransformed();
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
                this.drawOverlayTransformed();
            }
        });
    }

    ngAfterViewInit(): void {
        // setup resize handlers
        this.bgResize = new ResizeObserver(() => {
            const w = this.bgCanvasRef.nativeElement.clientWidth;
            const h = this.bgCanvasRef.nativeElement.clientHeight;
            // update canvas size or layout
            this.bgCanvasRef.nativeElement.width = w;
            this.bgCanvasRef.nativeElement.height = h;
            this.xlim = [0, w];
            this.ylim = [0, h];
            this.overlayCanvasRef.nativeElement.width = w;
            this.overlayCanvasRef.nativeElement.height = h;
            // redraw
            this.drawBackgroundTransformed();
            this.drawOverlayTransformed();
        });
        this.bgResize.observe(this.bgCanvasRef.nativeElement);

        // setup click handlers
        this.bgCanvasRef.nativeElement.addEventListener('mousedown', e => this.mouseDown(e));
        this.overlayCanvasRef.nativeElement.addEventListener('mousedown', e => this.mouseDown(e));

        this.bgCanvasRef.nativeElement.addEventListener('mousemove', e => this.mouseMove(e));
        this.overlayCanvasRef.nativeElement.addEventListener('mousemove', e => this.mouseMove(e));

        this.bgCanvasRef.nativeElement.addEventListener('mouseup', e => this.mouseUp(e));
        this.overlayCanvasRef.nativeElement.addEventListener('mouseup', e => this.mouseUp(e));

        this.bgCanvasRef.nativeElement.addEventListener('mouseleave', e => this.mouseLeave(e));
        this.overlayCanvasRef.nativeElement.addEventListener('mouseleave', e => this.mouseLeave(e));

        this.bgCanvasRef.nativeElement.addEventListener('wheel', e => this.mouseWheel(e), { passive: false });
        this.overlayCanvasRef.nativeElement.addEventListener('wheel', e => this.mouseWheel(e), { passive: false });

        // initiate image load
        this.imgsrv.send({
            type: 'get-high-res-map',
        });
    }

    ngOnDestroy(): void {
        // stop observers
        this.subs.unsubscribe();
        this.bgResize.disconnect();
    }

    stepBack() {
        this.imgsrv.send({
            type: "step-back",
        }); // we don't need to wait for the answer
        this.router.navigateByUrl("/step1");
    }

    stepForward() {
        throw Error("Sorry this is not implemented yet")
    }

    deleteWaypoint(index: number) {
        this.waypoints.splice(index, 1);
        this.updateWaypoints();
        this.drawOverlayTransformed();
    }

    moveWaypoint(index: number, up: boolean) {
        let move = up ? -1 : 1;
        this.waypoints.splice(index + move, 0, this.waypoints.splice(index, 1)[0]);
        this.updateWaypoints();
        this.drawOverlayTransformed();
    }

    renameWaypoint(index: number, event: Event) {
        if (!event.target) return;
        let target = (event.target as HTMLInputElement);
        if (!target.value) return;
        this.waypoints[index].name = target.value;
        this.updateWaypoints();
        this.drawOverlayTransformed();
    }

    private mouseDown(e: MouseEvent) {
        if (this.selectedTool == 'panzoom') {
            if (e.button === 1 || e.button === 0) {  // middle or left
                this.panStart = { x: e.offsetX, y: e.offsetY };
            }
        } else if (this.selectedTool == 'edit') {
            const x = e.offsetX
            const y = e.offsetY;
            if (e.button == 0) { // left click moves a waypoint
                for (var i = 0; i < this.waypoints.length; i++) {
                    const wp = this.waypoints[i];
                    const [xp, yp] = this.getImage2CanvasCoords(this.overlayCanvasRef.nativeElement, wp.x, wp.y);
                    const dist = Math.sqrt((xp - x) ** 2 + (yp - y) ** 2);
                    if (dist < this.selectionDistance) {
                        this.selectedPoint = i;
                        this.drawOverlayTransformed();
                        break;
                    }
                }
            } else if (e.button == 1) { // middle click creates a new
                const [wx, wy] = this.getCanvas2ImageCoords(this.overlayCanvasRef.nativeElement, x, y);
                this.waypoints.push({
                    name: '???',
                    x: wx,
                    y: wy,
                    lon: 0,
                    lat: 0,
                    lonlat_valid: false
                });
                this.drawOverlayTransformed();
                this.updateWaypoints();
            }
        }
    }

    private updateWaypoints() {
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

    private mouseMove(e: MouseEvent) {
        if (this.selectedTool == 'panzoom') {
            if (this.panStart) {
                const dx = e.offsetX - this.panStart.x;
                const dy = e.offsetY - this.panStart.y;
                this.panStart = { x: e.offsetX, y: e.offsetY };

                const [xmin, xmax] = this.xlim;
                const [ymin, ymax] = this.ylim;

                const deltaX = dx;
                const deltaY = dy;

                this.xlim = [xmin - deltaX, xmax - deltaX];
                this.ylim = [ymin - deltaY, ymax - deltaY];

                this.drawBackgroundTransformed();
                this.drawOverlayTransformed();
            }
        } else if (this.selectedTool == 'edit') {
            if (this.selectedPoint !== null) {
                const [x, y] = this.getCanvas2ImageCoords(this.overlayCanvasRef.nativeElement, e.offsetX, e.offsetY);
                this.waypoints[this.selectedPoint].x = x;
                this.waypoints[this.selectedPoint].y = y;
                this.waypoints[this.selectedPoint].lonlat_valid = false;
                this.drawOverlayTransformed();
            }
        }
    }

    private mouseUp(e: MouseEvent) {
        if (this.selectedTool == 'panzoom') {
            this.panStart = null;
        } else if (this.selectedTool == 'edit') {
            this.selectedPoint = null;
            this.drawOverlayTransformed();
            this.updateWaypoints();
        }
    }

    private mouseLeave(e: MouseEvent) {
        this.panStart = null;
    }

    private mouseWheel(e: WheelEvent) {
        if (this.selectedTool == 'panzoom') {
            e.preventDefault();
            const canvas = this.overlayCanvasRef.nativeElement;
            const mouseX = e.offsetX;
            const mouseY = e.offsetY;
            const zoomIn = e.deltaY < 0;

            const x = mouseX;
            const y = mouseY;

            const [xmin, xmax] = this.xlim;
            const [ymin, ymax] = this.ylim;
            const scaleFact = zoomIn ? 1 / this.zoomFactor : this.zoomFactor;
            const scale = scaleFact * e.deltaY / 100.;

            this.xlim = this.zoomWindow(this.xlim, x, zoomIn);
            this.ylim = this.zoomWindow(this.ylim, y, zoomIn);

            this.drawBackgroundTransformed();
            this.drawOverlayTransformed();
        }
    }

    private zoomWindow(
        xlim: [number, number],
        mouseX: number,
        zoomIn: boolean,
        zoomFactor: number = 1.1,
        minSpan: number = 1e-3
    ): [number, number] {
        const [xMin, xMax] = xlim;
        const span = xMax - xMin;
        const centerRatio = (mouseX - xMin) / span;

        const scale = zoomIn ? 1 / zoomFactor : zoomFactor;
        let newSpan = span * scale;

        // Prevent over-zoom
        if (newSpan < minSpan) newSpan = minSpan;

        const newMin = mouseX - centerRatio * newSpan;
        const newMax = mouseX + (1 - centerRatio) * newSpan;

        return [newMin, newMax];
    }

    private drawBackgroundImage(base64: string): void {
        const img = new Image();
        img.onload = () => {
            this.baseImage = img;
            this.drawBackgroundTransformed();
            this.drawOverlayTransformed();
        };
        img.src = 'data:image/png;base64,' + base64;
    }

    private drawBackgroundTransformed() {
        if (!this.baseImage) return;

        // get references and clear canvas
        const canvas = this.bgCanvasRef.nativeElement;
        const ctx = canvas.getContext('2d')!;
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // get the image data
        const img = this.baseImage;
        const imgWidth = img.width;
        const imgHeight = img.height;

        // Mapping from data coords to image pixels
        const [xmin, xmax] = this.xlim;
        const [ymin, ymax] = this.ylim;

        // Determine crop region in image space (sx, sy, sw, sh)
        const sx = xmin;
        const sy = ymin;
        const sw = xmax - xmin;
        const sh = ymax - ymin;

        // Destination: full canvas
        ctx.drawImage(img, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
    }

    private drawOverlayTransformed() {
        if (!this.baseImage) return;

        // get references and clear canvas
        const canvas = this.overlayCanvasRef.nativeElement;
        const ctx = canvas.getContext('2d')!;
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // get the image data
        const img = this.baseImage;
        const imgWidth = img.width;
        const imgHeight = img.height;

        if (this.waypoints.length > 0) {
            // draw polygon
            const [x, y] = this.getImage2CanvasCoords(canvas, this.waypoints[0].x, this.waypoints[0].y);
            ctx.beginPath();
            ctx.moveTo(x, y);
            for (let i = 1; i < this.waypoints.length; i++) {
                const [x, y] = this.getImage2CanvasCoords(canvas, this.waypoints[i].x, this.waypoints[i].y);
                ctx.lineTo(x, y);
            }
            ctx.closePath();
            ctx.lineWidth = 6;
            ctx.strokeStyle = "red";
            ctx.stroke();

            // draw corners and names
            for (let i = 0; i < this.waypoints.length; i++) {
                const wp = this.waypoints[i]
                const [x, y] = this.getImage2CanvasCoords(canvas, wp.x, wp.y);
                ctx.beginPath();
                ctx.fillStyle = i == this.selectedPoint ? "green" : "red";
                ctx.arc(x, y, 12, 0, 2 * Math.PI);
                ctx.fill();
                ctx.font = "12px serif";
                ctx.fillText(wp.name, x+15, y);
            }
        }

    }

    private getImage2CanvasCoords(canvas: HTMLCanvasElement, x: number, y: number) {
        const [xmin, xmax] = this.xlim;
        const [ymin, ymax] = this.ylim;
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);

        return [(x - xmin) * xscale, (y - ymin) * yscale];
    }

    private getCanvas2ImageCoords(canvas: HTMLCanvasElement, x: number, y: number) {
        const [xmin, xmax] = this.xlim;
        const [ymin, ymax] = this.ylim;
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);

        return [x / xscale + xmin, y / yscale + ymin];
    }

}
