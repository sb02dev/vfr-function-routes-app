import { HttpClient } from '@angular/common/http';
import { Injectable, OnDestroy } from '@angular/core';
import { environment } from '../../environments/environment';
import { map, mergeMap, Observable, Subject, Subscription, tap } from 'rxjs';

type TileDownloadQueueItem = { cachekey: string, url: string, callback: (blob: Blob) => void };
type TileDownloadQueueResult = { cachekey: string, blob: Blob, callback: (blob: Blob) => void };

@Injectable({
    providedIn: 'root',
})
export class TileService implements OnDestroy {

    private tileCache = new Map<string, ImageBitmap>();
    private tileDownloads = new Map<string, (blob: Blob) => void>();

    private downloadQueue = new Subject<TileDownloadQueueItem>();
    private downloadResult: Observable<TileDownloadQueueResult>;
    private downloadSubs: Subscription;
    
    constructor(private http: HttpClient) { 
        this.downloadResult = this.downloadQueue.pipe(
            mergeMap((value: TileDownloadQueueItem) =>
                this.http.get(value.url, { responseType: 'blob' }).pipe(
                    map((blob: Blob) => { return { cachekey: value.cachekey, blob: blob, callback: value.callback } })
                ), 3)
        );
        this.downloadSubs = this.downloadResult.subscribe((value: TileDownloadQueueResult) => this.downloadedTile(value));
    }
    
    async getTile(tilesetName: string, dpi: number, x: number, y: number, cbDownloaded: (blob: Blob) => void): Promise<ImageBitmap | undefined> {
        const cachekey = `${tilesetName}-${dpi}-${x}-${y}`;
        // try memory cache
        const memcached = this.tileCache.get(cachekey);
        if (memcached) {
            return memcached;
        }
        // TODO: try indexeddb-cache
        // if already downloading we return nothing, we do not wait
        const isDownloading = this.tileDownloads.has(cachekey);
        if (isDownloading) {
            return undefined;
        }
        // start downloading from server (maybe hits browser http cache)
        this.tileDownloads.set(cachekey, cbDownloaded);
        this.downloadQueue.next({
            cachekey: cachekey,
            url: `${environment.API_URL}/tile/${tilesetName}/${dpi}/${x}/${y}`,
            callback: cbDownloaded
        });
        // at this point we still have no tile downloaded
        return undefined;
    }

    async downloadedTile(value: TileDownloadQueueResult) {
        // TODO: save to indexeddb-cache
        // save downloaded image to memory cache
        if (value) {
            // create bitmap and put to memcache
            const bitmap = await createImageBitmap(value.blob);
            this.tileCache.set(value.cachekey, bitmap);
        }
        // mark as not downloading (it will hit memory cache anyway)
        this.tileDownloads.delete(value.cachekey);
        // call callback on successful download
        if (value.callback) {
            value.callback(value.blob);
        }
    }

    ngOnDestroy(): void {
        // unsubscribe
        this.downloadSubs.unsubscribe();
        // clear the tilecache and release the URLs
        this.tileCache.forEach((bitmap: ImageBitmap, key: string) => {
            bitmap.close();
        });
        this.tileCache.clear();
    }
}
