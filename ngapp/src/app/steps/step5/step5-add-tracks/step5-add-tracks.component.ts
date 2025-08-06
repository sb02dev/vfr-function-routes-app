import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, ElementRef, OnDestroy, ViewChild } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { Subscription } from 'rxjs';
import { ColorSketchModule } from 'ngx-color/sketch';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';

import { HeaderComponent } from '../../../components/header/header/header.component';
import { Track } from '../../../models/track';
import { MapEditComponent } from '../../../components/mapedit/map-edit/map-edit.component';
import { ImageEditService } from '../../../services/image-edit.service';
import { ColorPickerDialogComponent } from '../../../components/colorpicker/color-picker-dialog/color-picker-dialog.component';

@Component({
    selector: 'app-step5-add-tracks',
    standalone: true,
    imports: [
        CommonModule,
        MatIconModule,
        MatButtonModule,
        ColorSketchModule,
        MatDialogModule,
        HeaderComponent,
        MapEditComponent,
    ],
    templateUrl: './step5-add-tracks.component.html',
    styleUrl: './step5-add-tracks.component.css'
})
export class Step5AddTracksComponent implements AfterViewInit, OnDestroy {
    subs: Subscription;

    tracks: Track[] = [];

    @ViewChild('file_selector') file_selector!: ElementRef<HTMLInputElement>;
    @ViewChild(MapEditComponent) mapedit!: MapEditComponent;

    constructor(private imgsrv: ImageEditService, private dialog: MatDialog) {
        this.subs = imgsrv.channel.subscribe((msg) => {
            if (msg.type === 'tracks') {
                this.mapedit.drawBackgroundImage(msg['image']);
                this.tracks = msg['tracks'].map((trk: any) => {
                    return {
                        name: trk.name,
                        color: trk.color,
                        num_points: trk.num_points,
                    }
                });
                this.imgsrv.send({ type: "get-tracks-map" });
            }
        });
    }

    ngAfterViewInit(): void {
        // initiate image load
        this.imgsrv.send({ type: 'get-tracks' });
    }

    ngOnDestroy(): void {
        // stop observers
        this.subs.unsubscribe();
    }
    
    loadTrack() {
        let fs = this.file_selector.nativeElement;
        fs.onchange = null;
        fs.files = null;
        fs.onchange = async () => {
            if (fs.files && fs.files.length > 0) {
                let fstr = '';
                for (var i = 0; i < fs.files.length; i++) {
                    const fbuf = await fs.files[i].arrayBuffer()
                    fstr = this.arrayBufferToBase64(fbuf); // no base64 because it is JSON anyway
                    this.imgsrv.send({
                        type: 'load-track',
                        filename: fs.files[i].name,
                        data: fstr
                    });
                    break; // don't upload multiple files
                };
            }
        }
        fs.click()
    }

    deleteTrack(index: number) {
        this.tracks.splice(index, 1);
        this.updateTracks();
    }

    openColorPicker(index: number) {
        const dialogRef = this.dialog.open(ColorPickerDialogComponent, {
            width: '300px',
        });

        dialogRef.afterClosed().subscribe(result => {
            if (result) {
                this.tracks[index].color = result;
                this.updateTracks();
            }
        });
    }
    updateTracks() {
        this.imgsrv.send({
            type: 'update-tracks',
            tracks: this.tracks.map((t: Track) => {
                return {
                    name: t.name, // to identify on server if something was deleted
                    color: t.color
                }
            })
        });
    }

    drawOverlayTransformed(event: { canvas: HTMLCanvasElement, imgWidth: number, imgHeight: number }) {
        // nothing to do, drawing is on the server side at this point
    }

    private arrayBufferToBase64(buffer: ArrayBuffer): string {
        let binary = '';
        const bytes = new Uint8Array(buffer);
        const len = bytes.byteLength;
        for (let i = 0; i < len; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }

}
