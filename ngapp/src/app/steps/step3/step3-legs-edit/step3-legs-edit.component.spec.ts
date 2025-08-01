import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Step3LegsEditComponent } from './step3-legs-edit.component';

describe('Step3LegsEditComponent', () => {
  let component: Step3LegsEditComponent;
  let fixture: ComponentFixture<Step3LegsEditComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Step3LegsEditComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(Step3LegsEditComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
