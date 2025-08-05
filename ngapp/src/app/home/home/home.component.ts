import { Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { Router } from '@angular/router';
import { FlexLayoutModule } from '@ngbracket/ngx-layout';

@Component({
    selector: 'app-home',
    standalone: true,
    imports: [
        MatCardModule,
        FlexLayoutModule,
        MatButtonModule,
    ],
    templateUrl: './home.component.html',
    styleUrl: './home.component.css'
})
export class HomeComponent {

    constructor(private router: Router) { }
    
    start() {
        this.router.navigateByUrl('/step0')
    }
}
