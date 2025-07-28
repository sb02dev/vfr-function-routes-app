import { Component, AfterViewInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ImageEditService } from '../../../services/image-edit.service';

@Component({
  selector: 'app-step1-area-selection',
  standalone: true,
    imports: [
        DecimalPipe,
        MatButtonModule,
        MatIconModule,
        FlexLayoutModule,
        MatTooltipModule
    ],
  templateUrl: './step1-area-selection.component.html',
  styleUrl: './step1-area-selection.component.css'
})
export class Step1AreaSelectionComponent implements AfterViewInit, OnDestroy {
    
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

    // area of interest edit variables
    rect: [number, number, number, number] = [100, 100, 200, 200];
    lonlat: [number, number, number, number] = [0, 0, 0, 0];
    private selectionDistance: number = 10.;
    selectedPoint: number | null = null;

    constructor(public router: Router, private imgsrv: ImageEditService) {
        this.subs = imgsrv.channel.subscribe((msg) => {
            if (msg.type === 'low-res') {
                this.drawBackgroundImage(msg['image']);
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
            } else if (msg.type === 'area-of-interest') {
                this.lonlat = [
                    msg['top-left'].lon,
                    msg['top-left'].lat,
                    msg['bottom-right'].lon,
                    msg['bottom-right'].lat
                ];
                if (msg['step']) {
                    this.router.navigateByUrl("/step2");
                }
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
            type: 'get-low-res-map',
        });
    }

    ngOnDestroy(): void {
        // stop observers
        this.subs.unsubscribe();
        this.bgResize.disconnect();
    }

    stepBack() {
        this.router.navigateByUrl("/step0");
    }

    stepForward() {
        this.setAreaOfInterest(true);
    }

    private mouseDown(e: MouseEvent) {
        if (this.selectedTool == 'panzoom') {
            if (e.button === 1 || e.button === 0) {  // middle or left
                this.panStart = { x: e.offsetX, y: e.offsetY };
            }
        } else if (this.selectedTool == 'edit') {
            const x = e.offsetX
            const y = e.offsetY;
            const [sx, sy, sw, sh] = this.getRectImageCoords(this.overlayCanvasRef.nativeElement);
            const xys = [[sx, sy], [sx + sw, sy], [sx + sw, sy + sh], [sx, sy + sh]];
            for (var i = 0; i < xys.length; i++) {
                const xy = xys[i];
                const dist = Math.sqrt((xy[0] - x) ** 2 + (xy[1] - y) ** 2);
                if (dist < this.selectionDistance) {
                    this.selectedPoint = i;
                    this.drawOverlayTransformed();
                    break;
                }
            }
        }
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
                const [sx, sy, sw, sh] = this.rect;
                if (this.selectedPoint == 0) {
                    this.rect = [x, y, sw - (x - sx), sh - (y - sy)];
                } else if (this.selectedPoint == 1) {
                    this.rect = [sx, y, x-sx, sh - (y - sy)];
                } else if (this.selectedPoint == 2) {
                    this.rect = [sx, sy, x - sx, y - sy];
                } else if (this.selectedPoint == 3) {
                    this.rect = [x, sy, sw - (x - sx), y - sy];
                }
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
            this.setAreaOfInterest();
        }
    }

    private setAreaOfInterest(step: boolean = false) {
        this.imgsrv.send({
            type: 'set-area-of-interest',
            step: step,
            topleft: { x: this.rect[0], y: this.rect[1] },
            bottomright: { x: this.rect[0] + this.rect[2], y: this.rect[1] + this.rect[3] },
        });
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

        // Mapping from data coords to image pixels
        const [sx, sy, sw, sh] = this.getRectImageCoords(canvas);

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
            ctx.fillStyle = i==this.selectedPoint?"green":"red";
            ctx.arc(xy[0], xy[1], 12, 0, 2*Math.PI);
            ctx.fill();
        }
    }

    private getRectImageCoords(canvas: HTMLCanvasElement) {
        const [xmin, xmax] = this.xlim;
        const [ymin, ymax] = this.ylim;
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);

        // Determine crop region in image space (sx, sy, sw, sh)
        const [rx, ry, rw, rh] = this.rect;
        const sx = (rx - xmin) * xscale;
        const sy = (ry - ymin) * yscale; // y is flipped because canvas y=0 is top
        const sw = rw * xscale;
        const sh = rh * yscale;

        return [sx, sy, sw, sh];
    }

    private getCanvas2ImageCoords(canvas: HTMLCanvasElement, x: number, y: number) {
        const [xmin, xmax] = this.xlim;
        const [ymin, ymax] = this.ylim;
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);

        return [x / xscale + xmin, y / yscale + ymin];
    }


}
