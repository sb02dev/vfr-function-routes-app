import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

import { HeaderComponent } from '../../../components/header/header/header.component';

@Component({
    selector: 'app-step5-add-tracks',
    standalone: true,
    imports: [
        CommonModule,
        HeaderComponent,
    ],
    templateUrl: './step5-add-tracks.component.html',
    styleUrl: './step5-add-tracks.component.css'
})
export class Step5AddTracksComponent {

}
