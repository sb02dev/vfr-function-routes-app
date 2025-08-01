import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Step6DownloadAndSaveComponent } from './step6-download-and-save.component';

describe('Step6DownloadAndSaveComponent', () => {
  let component: Step6DownloadAndSaveComponent;
  let fixture: ComponentFixture<Step6DownloadAndSaveComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Step6DownloadAndSaveComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(Step6DownloadAndSaveComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
