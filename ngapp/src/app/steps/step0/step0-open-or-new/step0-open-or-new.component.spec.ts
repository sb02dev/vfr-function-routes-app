import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Step0OpenOrNewComponent } from './step0-open-or-new.component';

describe('Step1OpenOrNewComponent', () => {
  let component: Step0OpenOrNewComponent;
  let fixture: ComponentFixture<Step0OpenOrNewComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Step0OpenOrNewComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(Step0OpenOrNewComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
