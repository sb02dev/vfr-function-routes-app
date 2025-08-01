import { Routes } from '@angular/router';

import { Step0OpenOrNewComponent } from './steps/step0/step0-open-or-new/step0-open-or-new.component';
import { Step1AreaSelectionComponent } from './steps/step1/step1-area-selection/step1-area-selection.component';
import { Step2WaypointsEditComponent } from './steps/step2/step2-waypoints-edit/step2-waypoints-edit.component';
import { Step3LegsEditComponent } from './steps/step3/step3-legs-edit/step3-legs-edit.component';
import { Step4AnnotationsEditComponent } from './steps/step4/step4-annotations-edit/step4-annotations-edit.component';

export const routes: Routes = [
    { path: "", component: Step0OpenOrNewComponent },    
    { path: "step0", component: Step0OpenOrNewComponent },
    { path: "step1", component: Step1AreaSelectionComponent },
    { path: "step2", component: Step2WaypointsEditComponent },
    { path: "step3", component: Step3LegsEditComponent },
    { path: "step4", component: Step4AnnotationsEditComponent},
];
