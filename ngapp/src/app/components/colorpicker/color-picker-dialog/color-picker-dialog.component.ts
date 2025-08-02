import { Component } from '@angular/core';
import { MatDialogModule } from '@angular/material/dialog';
import { ColorSketchModule } from 'ngx-color/sketch';

@Component({
    selector: 'app-color-picker-dialog',
    standalone: true,
    imports: [
        ColorSketchModule,
        MatDialogModule,
    ],
    templateUrl: './color-picker-dialog.component.html',
    styleUrl: './color-picker-dialog.component.css'
})
export class ColorPickerDialogComponent {
    color = '#0000ff';
}
