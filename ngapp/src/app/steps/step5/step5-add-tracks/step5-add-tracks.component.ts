import { CommonModule } from '@angular/common';
import { AfterContentInit, Component, ElementRef, OnDestroy, ViewChild } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { ColorSketchModule } from 'ngx-color/sketch';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { ColorPickerDialogComponent } from '../../../components/colorpicker/color-picker-dialog/color-picker-dialog.component';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';

import { HeaderComponent } from '../../../components/header/header/header.component';
import { Track } from '../../../models/track';
import { MapEditComponent } from '../../../components/mapedit/map-edit/map-edit.component';
import { ImageEditService } from '../../../services/image-edit.service';
import { ImageEditMessage } from '../../../models/image-edit-msg';

@Component({
    selector: 'app-step5-add-tracks',
    standalone: true,
    imports: [
        CommonModule,
        MatIconModule,
        MatButtonModule,
        MatTooltipModule,
        ColorSketchModule,
        MatDialogModule,
        MatCardModule,
        MatTableModule,
        HeaderComponent,
        MapEditComponent,
    ],
    templateUrl: './step5-add-tracks.component.html',
    styleUrl: './step5-add-tracks.component.css'
})
export class Step5AddTracksComponent implements AfterContentInit {

    tracks: Track[] = [];

    @ViewChild('file_selector') file_selector!: ElementRef<HTMLInputElement>;
    @ViewChild(MapEditComponent) mapedit!: MapEditComponent;

    constructor(private imgsrv: ImageEditService, private dialog: MatDialog) {
    }

    ngAfterContentInit(): void {
        // initiate image load
        this.imgsrv.send('get-tracks', this.gotTracks.bind(this));
        this.imgsrv.send('get-tracks-map', (result) => { this.mapedit.gotTiledImage(result) });
    }

    gotTracks(result: ImageEditMessage) {
        this.tracks = result['tracks'].map((trk: any) => {
            return {
                name: trk.name,
                color: trk.color,
                num_points: trk.num_points,
            }
        });
        if (result['svg_overlay'] && result['svg_overlay'] !== '-') {
            this.mapedit.setSVG(result['svg_overlay']);
        }
    }
    
    loadTrack() {
        let fs = this.file_selector.nativeElement;
        fs.onchange = null;
        fs.files = null;
        fs.value = "";
        fs.onchange = async () => {
            if (fs.files && fs.files.length > 0) {
                let fstr = '';
                for (var i = 0; i < fs.files.length; i++) {
                    const fbuf = await fs.files[i].arrayBuffer()
                    fstr = this.arrayBufferToBase64(fbuf); // no base64 because it is JSON anyway
                    this.imgsrv.send('load-track', this.gotTracks.bind(this), {
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

    compareTracks(index: number, tr: Track) {
        return index;
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
        this.imgsrv.send('update-tracks', this.gotTracks.bind(this), {
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
