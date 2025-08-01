import { AfterViewInit, Component, ElementRef, EventEmitter, Input, OnDestroy, Output, ViewChild } from '@angular/core';
import { MatIconModule } from "@angular/material/icon";
import { CommonModule } from '@angular/common';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';
import { MatButtonModule } from '@angular/material/button';

@Component({
    selector: 'app-map-edit',
    standalone: true,
    imports: [
        CommonModule,
        MatIconModule,
        MatButtonModule,
        FlexLayoutModule,
    ],
    templateUrl: './map-edit.component.html',
    styleUrl: './map-edit.component.css'
})
export class MapEditComponent implements AfterViewInit, OnDestroy {
    @Output() drawOverlay = new EventEmitter();
    @Output() enumPoints = new EventEmitter<(i: number, x: number, y: number) => boolean>();
    @Output() addPointAt = new EventEmitter<{ x: number, y: number, callback: () => void }>();
    @Output() movePointTo = new EventEmitter<{ i: number, x: number, y: number, callback: () => void }>();
    @Output() finalizePoints = new EventEmitter();

    @ViewChild('bgCanvas', { static: true }) bgCanvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('overlayCanvas', { static: true }) overlayCanvasRef!: ElementRef<HTMLCanvasElement>;
    private bgResize!: ResizeObserver;
    baseImage: HTMLImageElement | null = null;
    public selectedTool: string = 'panzoom';

    // pan and zoom variables
    private xlim: [number, number] = [0, 4];
    private ylim: [number, number] = [0, 4];
    private panStart: { x: number, y: number } | null = null;
    private zoomFactor: number = 1.1; // how much to zoom in/out per scroll step

    // point edit variables
    private selectionDistance: number = 10.;
    selectedPoint: number | null = null;
    

    ngAfterViewInit(): void {
        // setup resize handlers
        this.bgResize = new ResizeObserver(() => {
            const w = this.bgCanvasRef.nativeElement.clientWidth;
            const h = this.bgCanvasRef.nativeElement.clientHeight;
            // update canvas size or layout
            this.bgCanvasRef.nativeElement.width = w;
            this.bgCanvasRef.nativeElement.height = h;
            this.xlim = [this.xlim[0], this.xlim[0] + w];
            this.ylim = [this.ylim[0], this.ylim[0] + h];
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

    }

    ngOnDestroy(): void {
        // stop observers
        this.bgResize.disconnect();
    }

    resetView() {
        this.xlim = [0, this.bgCanvasRef.nativeElement.width];
        this.ylim = [0, this.bgCanvasRef.nativeElement.height];
        this.drawBackgroundTransformed();
        this.drawOverlayTransformed();
    }

    zoomToAll() {
        if (!this.baseImage) return;
        const imw = this.baseImage.width;
        const imh = this.baseImage.height;
        const canvasw = this.bgCanvasRef.nativeElement.width;
        const canvash = this.bgCanvasRef.nativeElement.height;
        const widthratio = imw / canvasw;
        const heightratio = imh / canvash;
        if (widthratio > heightratio) {
            this.xlim = [0,imw];
            this.ylim = [0,canvash*widthratio];
        } else {
            this.xlim = [0,canvasw*heightratio];
            this.ylim = [0,imh];
        }
        this.drawBackgroundTransformed();
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
            if (e.button == 0) { // left click moves a point
                this.enumPoints.emit((i: number, xx: number, yy: number) => {
                    const [xp, yp] = this.getImage2CanvasCoords(xx, yy);
                    const dist = Math.sqrt((xp - x) ** 2 + (yp - y) ** 2);
                    if (dist < this.selectionDistance) {
                        this.selectedPoint = i
                        this.drawOverlayTransformed();
                        return false;
                    } else {
                        return true;
                    }
                })
            } else if (e.button == 1) { // middle click creates a new
                const [wx, wy] = this.getCanvas2ImageCoords(x, y);
                this.addPointAt.emit({
                    x: wx, y: wy, callback: () => {
                        this.drawOverlayTransformed();
                    }
                });
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
                const [x, y] = this.getCanvas2ImageCoords(e.offsetX, e.offsetY);
                this.movePointTo.emit({
                    i: this.selectedPoint,
                    x: x,
                    y: y,
                    callback: () => this.drawOverlayTransformed(),
                })
            }
        }
    }

    private mouseUp(e: MouseEvent) {
        if (this.selectedTool == 'panzoom') {
            this.panStart = null;
        } else if (this.selectedTool == 'edit') {
            this.selectedPoint = null;
            this.drawOverlayTransformed();
            this.finalizePoints.emit();
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

    drawBackgroundImage(base64: string): void {
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

    drawOverlayTransformed() {
        this.drawOverlay.emit({
            canvas: this.overlayCanvasRef.nativeElement,
            imgWidth: this.baseImage?.width,
            imgHeight: this.baseImage?.height,
        });
    }

    getImage2CanvasCoords(x: number, y: number) {
        const canvas: HTMLCanvasElement = this.bgCanvasRef.nativeElement;
        const [xmin, xmax] = this.xlim;
        const [ymin, ymax] = this.ylim;
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);

        return [(x - xmin) * xscale, (y - ymin) * yscale];
    }

    getCanvas2ImageCoords(x: number, y: number) {
        const canvas: HTMLCanvasElement = this.bgCanvasRef.nativeElement;
        const [xmin, xmax] = this.xlim;
        const [ymin, ymax] = this.ylim;
        const xscale = canvas.width / (xmax - xmin);
        const yscale = canvas.height / (ymax - ymin);

        return [x / xscale + xmin, y / yscale + ymin];
    }

}
