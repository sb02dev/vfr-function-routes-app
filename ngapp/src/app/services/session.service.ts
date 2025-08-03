import { Injectable } from '@angular/core';

@Injectable({
    providedIn: 'root'
})
export class SessionService {
    private readonly key = 'session_id';

    constructor() { }
    
    getStoredSessionId(): string | null {
        return localStorage.getItem(this.key);
    }

    storeSessionId(id: string) {
        localStorage.setItem(this.key, id);
    }
}
