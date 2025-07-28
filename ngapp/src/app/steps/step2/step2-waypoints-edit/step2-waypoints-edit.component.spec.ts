import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Step2WaypointsEditComponent } from './step2-waypoints-edit.component';

describe('Step2WaypointsEditComponent', () => {
  let component: Step2WaypointsEditComponent;
  let fixture: ComponentFixture<Step2WaypointsEditComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Step2WaypointsEditComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(Step2WaypointsEditComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
