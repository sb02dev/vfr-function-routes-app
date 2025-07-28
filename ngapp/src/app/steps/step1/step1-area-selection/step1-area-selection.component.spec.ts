import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Step1AreaSelectionComponent } from './step1-area-selection.component';

describe('Step2AreaSelectionComponent', () => {
  let component: Step1AreaSelectionComponent;
  let fixture: ComponentFixture<Step1AreaSelectionComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Step1AreaSelectionComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(Step1AreaSelectionComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
